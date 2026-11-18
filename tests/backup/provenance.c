#include "mbr_provenance.h"
#include "config.h"

static struct { rb_u32 lo; rb_mbr_history h; rb_u32 hi; } state;
static struct { rb_u32 lo; rb_u8 bytes[512]; rb_u32 hi; } output;
static rb_mbr_binding binding;
static rb_mbr_io io;
static rb_mbr_review_ticket ticket;
static rb_mbr_record stored;
static rb_u8 live[512], first[512], approved[512];
static rb_u16 calls, live_calls, fail_live, alter_live, live_count, external_count;
static rb_u16 requested_role, checks, switched_disk_at, switched_medium;
static rb_u32 requested_revision;

#define H (&state.h)
#define CHECK(condition) do { ++checks; if (!(condition)) { return __LINE__; } } while (0)

static void fill(void *p, rb_u16 n, rb_u8 value)
{
    rb_u8 *bytes = (rb_u8 *)p;
    while (n) { bytes[--n] = value; }
}

static int same(const void *a, const void *b, rb_u16 size)
{
    const rb_u8 *x = (const rb_u8 *)a, *y = (const rb_u8 *)b;
    while (size) { --size; if (x[size] != y[size]) { return 0; } }
    return 1;
}

static int empty(const void *p, rb_u16 n)
{
    const rb_u8 *bytes = (const rb_u8 *)p;
    while (n) { if (bytes[--n]) { return 0; } }
    return 1;
}

static void copy(rb_u8 *out, const rb_u8 *in)
{
    rb_u16 i;
    for (i = 0; i < 512; ++i) { out[i] = in[i]; }
}

static void message(const char *s)
{
    while (*s) { rb_putc(*s++); }
    rb_putc(13); rb_putc(10);
}

static void hex(rb_u16 value)
{
    static const char digits[] = "0123456789ABCDEF";
    rb_u16 i = 4;
    while (i) { --i; rb_putc(digits[(value >> (4 * i)) & 15]); }
}

static void reset_io(void)
{
    calls = live_calls = fail_live = alter_live = requested_role = switched_disk_at = switched_medium = 0;
    requested_revision = 0;
    live_count = external_count = 512;
}

static rb_u16 __cdecl read_live(rb_mbr_target *actual, rb_u8 *out, void *context)
{
    rb_u16 i, n;
    calls = calls * 10 + 1; ++live_calls;
    if (context != live) { return 0; }
    *actual = binding.target;
    if (live_calls == switched_disk_at) { actual->id[15] ^= 1; }
    n = live_calls == fail_live ? live_count : 512;
    for (i = 0; i < n && i < 512; ++i) { out[i] = live[i]; }
    if (live_calls == alter_live) { out[511] ^= 1; }
    return n;
}

static rb_u16 __cdecl read_external(rb_u16 role, rb_u32 revision,
                                    rb_mbr_record *record, rb_u8 *medium_id, void *context)
{
    rb_u16 i;
    calls = calls * 10 + 2;
    requested_role = role; requested_revision = revision;
    if (context != &stored) { return 0; }
    for (i = 0; i < 16; ++i) { medium_id[i] = binding.recovery_id[i]; }
    if (switched_medium) { medium_id[15] ^= 1; }
    *record = stored;
    return external_count;
}

static void stage(rb_u16 role, rb_u32 revision, const rb_u8 *sector)
{
    stored.binding = binding;
    stored.role = role; stored.revision = revision;
    copy(stored.sector, sector);
    reset_io();
}

static void setup(void)
{
    rb_u16 i;
    fill(&state, sizeof(state), 0);
    fill(&binding, sizeof(binding), 0);
    state.lo = output.lo = 0x12345678UL;
    state.hi = output.hi = 0xABCDEF01UL;
    binding.target.id[15] = 0x11;
    binding.recovery_id[15] = 0x22;
    binding.target.capacity_low = 262144UL;
    io.binding = &binding; io.current = read_live; io.external = read_external;
    io.disk = live; io.medium = &stored;
    for (i = 0; i < 512; ++i) { first[i] = (rb_u8)(i * 7 + 3); }
    copy(live, first);
    stage(RB_BACKUP_ORIGINAL, 1, first);
}

static int guards(void)
{
    return state.lo == 0x12345678UL && state.hi == 0xABCDEF01UL
        && output.lo == 0x12345678UL && output.hi == 0xABCDEF01UL;
}

static rb_u16 enroll(void)
{
    return rb_mbr_enroll(H, &io, RB_MBR_FIRST_INSTALL);
}

static rb_u16 decide(rb_u16 decision)
{
    return rb_mbr_decide(H, &io, &ticket, decision);
}

static rb_u16 read_role(rb_u16 role, rb_u32 revision)
{
    fill(output.bytes, 512, 0xCC);
    return rb_mbr_read_role(H, &io, role, revision, output.bytes);
}

static rb_u16 lifecycle(void)
{
    rb_mbr_review_ticket old, foreign;
    setup();
    CHECK(read_role(RB_BACKUP_ORIGINAL, 1) == RB_MBR_STATE && empty(output.bytes, 512));
    CHECK(!enroll() && calls == 121 && requested_role == RB_BACKUP_ORIGINAL && requested_revision == 1);
    CHECK(H->revision == 1 && !H->approved_revision && !H->pending && same(H->original, first, 512));
    reset_io();
    CHECK(enroll() == RB_MBR_STATE && !calls);
    CHECK(read_role(RB_BACKUP_APPROVED, 1) == RB_MBR_STATE && !calls && empty(output.bytes, 512));
    live[0] ^= 1;
    CHECK(!read_role(RB_BACKUP_ORIGINAL, 1) && calls == 2 && same(output.bytes, first, 512));
    message("ORIGINAL SEALED");

    reset_io();
    CHECK(!rb_mbr_review(H, &io, &ticket) && calls == 1 && ticket.revision == 2);
    CHECK(same(&ticket.binding, &binding, sizeof(binding)) && same(H->candidate, live, 512));
    CHECK(decide(RB_MBR_NO_DECISION) == RB_MBR_PARAMS && H->pending && calls == 1);
    CHECK(!decide(RB_MBR_REJECT) && !H->pending && empty(H->candidate, 512) && calls == 1);
    CHECK(decide(RB_MBR_APPROVE) == RB_MBR_STATE && !H->approved_revision);
    message("CURRENT REJECTED");

    live[445] ^= 0x17;
    CHECK(!rb_mbr_review(H, &io, &ticket) && ticket.revision == 3);
    stage(RB_BACKUP_APPROVED, 3, live);
    CHECK(!decide(RB_MBR_APPROVE) && calls == 121 && requested_role == RB_BACKUP_APPROVED && requested_revision == 3);
    CHECK(H->approved_revision == 3 && same(H->approved, live, 512) && empty(H->candidate, 512));
    copy(approved, live);
    CHECK(decide(RB_MBR_APPROVE) == RB_MBR_STATE);
    reset_io();
    CHECK(!read_role(RB_BACKUP_APPROVED, 3) && calls == 2 && same(output.bytes, approved, 512));
    message("REVISION 3 APPROVED");

    live[511] ^= 1;
    CHECK(!rb_mbr_review(H, &io, &old) && old.revision == 4);
    CHECK(!read_role(RB_BACKUP_APPROVED, 3) && same(output.bytes, approved, 512));
    live[511] ^= 1;
    CHECK(!rb_mbr_review(H, &io, &ticket) && ticket.revision == 5 && same(H->candidate, approved, 512));
    reset_io();
    CHECK(rb_mbr_decide(H, &io, &old, RB_MBR_APPROVE) == RB_MBR_REVISION && H->pending && !calls);
    foreign = ticket; foreign.binding.target.id[15] ^= 1;
    CHECK(rb_mbr_decide(H, &io, &foreign, RB_MBR_APPROVE) == RB_MBR_BINDING && H->pending && !calls);
    foreign = ticket; foreign.binding.recovery_id[15] ^= 1;
    CHECK(rb_mbr_decide(H, &io, &foreign, RB_MBR_REJECT) == RB_MBR_BINDING && H->pending && !calls);
    stage(RB_BACKUP_APPROVED, 5, live);
    CHECK(!decide(RB_MBR_APPROVE) && calls == 121 && H->approved_revision == 5);
    reset_io();
    CHECK(read_role(RB_BACKUP_APPROVED, 3) == RB_MBR_REVISION && !calls && empty(output.bytes, 512));
    CHECK(read_role(RB_BACKUP_EBR, 5) == RB_MBR_ROLE && !calls && empty(output.bytes, 512));
    stage(RB_BACKUP_ORIGINAL, 1, first);
    CHECK(!read_role(RB_BACKUP_ORIGINAL, 1) && same(output.bytes, first, 512) && guards());
    copy(live, approved);
    CHECK(!rb_mbr_review(H, &io, &ticket) && ticket.revision == 6);
    stage(RB_BACKUP_APPROVED, 6, live);
    live[0] ^= 1;
    CHECK(decide(RB_MBR_APPROVE) == RB_MBR_CHANGED && calls == 1 && !H->pending);
    live[0] ^= 1;
    CHECK(decide(RB_MBR_APPROVE) == RB_MBR_STATE && H->approved_revision == 5);
    io.current = (rb_mbr_current_reader)0;
    stage(RB_BACKUP_APPROVED, 5, approved);
    CHECK(!read_role(RB_BACKUP_APPROVED, 5) && calls == 2 && same(output.bytes, approved, 512));
    message("STALE REVIEW BLOCKED");
    return 0;
}

enum { SHORT_OPEN, EXTERNAL_ERROR, SHORT_EXTERNAL, WRONG_TARGET, WRONG_MEDIUM,
       WRONG_LOW, WRONG_HIGH, WRONG_ROLE, WRONG_REVISION, WRONG_BYTES, SHORT_CLOSE,
       CHANGED_CLOSE, OVERLONG_EXTERNAL, DISK_OPEN, DISK_CLOSE, COPIED_MEDIUM, FAULTS };

static const rb_u16 fault_codes[FAULTS] = {
    RB_MBR_LIVE_IO, RB_MBR_EXTERNAL_IO, RB_MBR_EXTERNAL_IO, RB_MBR_BINDING, RB_MBR_BINDING,
    RB_MBR_BINDING, RB_MBR_BINDING, RB_MBR_ROLE, RB_MBR_REVISION, RB_MBR_CHANGED, RB_MBR_LIVE_IO,
    RB_MBR_CHANGED, RB_MBR_EXTERNAL_IO, RB_MBR_BINDING, RB_MBR_BINDING, RB_MBR_BINDING
};

static void inject(rb_u16 fault)
{
    switch (fault) {
    case SHORT_OPEN: fail_live = 1; live_count = 511; break;
    case EXTERNAL_ERROR: external_count = 0; break;
    case SHORT_EXTERNAL: external_count = 511; break;
    case WRONG_TARGET: stored.binding.target.id[15] ^= 1; break;
    case WRONG_MEDIUM: stored.binding.recovery_id[15] ^= 1; break;
    case WRONG_LOW: ++stored.binding.target.capacity_low; break;
    case WRONG_HIGH: ++stored.binding.target.capacity_high; break;
    case WRONG_ROLE: stored.role = stored.role == 1 ? 2 : 1; break;
    case WRONG_REVISION: ++stored.revision; break;
    case WRONG_BYTES: stored.sector[511] ^= 1; break;
    case SHORT_CLOSE: fail_live = 2; live_count = 511; break;
    case CHANGED_CLOSE: alter_live = 2; break;
    case OVERLONG_EXTERNAL: external_count = 513; break;
    case DISK_OPEN: switched_disk_at = 1; break;
    case DISK_CLOSE: switched_disk_at = 2; break;
    case COPIED_MEDIUM: switched_medium = 1; break;
    }
}

static rb_u16 failed_transitions(void)
{
    rb_u16 i, expected_calls;
    for (i = 0; i < FAULTS; ++i) {
        expected_calls = 12;
        if (i == SHORT_OPEN || i == DISK_OPEN) { expected_calls = 1; }
        if (i == SHORT_CLOSE || i == CHANGED_CLOSE || i == DISK_CLOSE) { expected_calls = 121; }
        setup(); inject(i);
        CHECK(enroll() == fault_codes[i] && calls == expected_calls);
        CHECK(empty(H, sizeof(*H)) && guards());
        stage(RB_BACKUP_ORIGINAL, 1, first);
        CHECK(!enroll());
        CHECK(!rb_mbr_review(H, &io, &ticket));
        stage(RB_BACKUP_APPROVED, 2, first);
        CHECK(!decide(RB_MBR_APPROVE));
        live[439] ^= 1;
        CHECK(!rb_mbr_review(H, &io, &ticket));
        stage(RB_BACKUP_APPROVED, 3, live); inject(i);
        CHECK(decide(RB_MBR_APPROVE) == fault_codes[i] && calls == expected_calls);
        CHECK(H->approved_revision == 2 && same(H->approved, first, 512)
              && same(H->original, first, 512) && !H->pending && empty(H->candidate, 512));
        reset_io();
        CHECK(decide(RB_MBR_APPROVE) == RB_MBR_STATE && !calls && guards());
        if (expected_calls == 12) {
            stage(RB_BACKUP_APPROVED, 2, first); inject(i);
            CHECK(read_role(RB_BACKUP_APPROVED, 2) == fault_codes[i] && calls == 2 && empty(output.bytes, 512));
            stage(RB_BACKUP_ORIGINAL, 1, first); inject(i);
            CHECK(read_role(RB_BACKUP_ORIGINAL, 1) == fault_codes[i] && calls == 2 && empty(output.bytes, 512));
        }
    }
    message("READBACK FAILURES BLOCKED");
    return 0;
}

static rb_u16 boundaries(void)
{
    rb_mbr_binding other;
    rb_u32 crc;
    rb_u16 i;
    setup();
    CHECK(rb_mbr_enroll(H, &io, RB_MBR_ORIGIN_UNKNOWN) == RB_MBR_ORIGIN && !calls);
    CHECK(rb_mbr_enroll(H, &io, RB_MBR_ALREADY_MANAGED) == RB_MBR_ORIGIN && !calls);
    CHECK(rb_mbr_review(H, &io, &ticket) == RB_MBR_STATE && empty(&ticket, sizeof(ticket)));
    CHECK(rb_mbr_enroll((rb_mbr_history *)0, &io, RB_MBR_FIRST_INSTALL) == RB_MBR_PARAMS);
    other = binding; io.binding = &other;
    other.target.id[15] = 0; CHECK(enroll() == RB_MBR_BINDING && !calls);
    other = binding; other.recovery_id[15] = 0; CHECK(enroll() == RB_MBR_BINDING && !calls);
    other.recovery_id[15] = other.target.id[15]; CHECK(enroll() == RB_MBR_BINDING && !calls);
    other = binding; other.target.capacity_low = 0; CHECK(enroll() == RB_MBR_BINDING && !calls);
    io.binding = &binding;
    live[432] = 'R'; live[433] = 'B'; live[434] = 'M'; live[435] = '1';
    CHECK(enroll() == RB_MBR_ORIGIN && calls == 1 && empty(H, sizeof(*H)));
    fill(live, 512, 0); binding.target.capacity_low = 0; binding.target.capacity_high = 1;
    stage(RB_BACKUP_ORIGINAL, 1, live);
    CHECK(!enroll() && H->revision == 1 && !H->approved_revision && empty(H->original, 512));

    CHECK(!rb_mbr_review(H, &io, &ticket));
    reset_io(); fail_live = 1; live_count = 511;
    CHECK(rb_mbr_review(H, &io, &ticket) == RB_MBR_LIVE_IO && !H->pending && empty(&ticket, sizeof(ticket)));
    CHECK(empty(H->candidate, 512) && H->revision == 2);
    reset_io(); other = binding; other.target.capacity_high = 2; io.binding = &other;
    CHECK(rb_mbr_review(H, &io, &ticket) == RB_MBR_BINDING && !calls);
    CHECK(read_role(RB_BACKUP_ORIGINAL, 1) == RB_MBR_BINDING && empty(output.bytes, 512) && !calls);
    io.binding = &binding; H->revision = 0xFFFFUL;
    CHECK(!rb_mbr_review(H, &io, &ticket) && ticket.revision == 0x10000UL);
    H->revision = 0xFFFFFFFEUL;
    CHECK(!rb_mbr_review(H, &io, &ticket) && ticket.revision == 0xFFFFFFFFUL);
    stage(RB_BACKUP_APPROVED, ticket.revision, live);
    CHECK(!decide(RB_MBR_APPROVE) && H->approved_revision == 0xFFFFFFFFUL);
    reset_io();
    CHECK(rb_mbr_review(H, &io, &ticket) == RB_MBR_REVISION && !calls && !H->pending);
    CHECK(!read_role(RB_BACKUP_APPROVED, 0xFFFFFFFFUL) && calls == 2);
    CHECK(rb_mbr_read_role(H, &io, RB_BACKUP_APPROVED, 0xFFFFFFFFUL, (rb_u8 *)0) == RB_MBR_PARAMS);

    /* Valid trailing CRCs give different bodies the same whole-sector CRC. */
    setup();
    crc = rb_crc32(live, 508);
    for (i = 0; i < 4; ++i) { live[508 + i] = (rb_u8)(crc >> (8 * i)); }
    stage(RB_BACKUP_ORIGINAL, 1, live);
    stored.sector[440] ^= 1;
    crc = rb_crc32(stored.sector, 508);
    for (i = 0; i < 4; ++i) { stored.sector[508 + i] = (rb_u8)(crc >> (8 * i)); }
    CHECK(rb_crc32(live, 512) == rb_crc32(stored.sector, 512) && !same(live, stored.sector, 512));
    CHECK(enroll() == RB_MBR_CHANGED && calls == 12 && empty(H, sizeof(*H)) && guards());
    return 0;
}

rb_u16 __cdecl rb_mbr_provenance_selftest(void)
{
    rb_u16 line;
    checks = 0;
    line = lifecycle();
    if (!line) { line = failed_transitions(); }
    if (!line) { line = boundaries(); }
    if (line) { rb_putc('!'); hex(line); message(""); return 1; }
    rb_putc('N'); rb_putc('='); hex(checks); message("");
    return 0;
}
