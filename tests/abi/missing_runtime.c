/* Negative link test: no default library or undefined symbol may slip through. */
extern void __cdecl rb_missing_runtime(void);

void __cdecl rb_negative_link(void)
{
    rb_missing_runtime();
}
