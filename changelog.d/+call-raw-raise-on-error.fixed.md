Fix `call()` and `call_raw()` to re-raise exceptions instead of calling `sys.exit(1)`, restoring the pre-refactor behavior for programmatic invocations.
