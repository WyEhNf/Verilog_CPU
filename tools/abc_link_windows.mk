# Keep the upstream ABC object list and link options. Use GCC's response file
# because the Windows process command line cannot hold all 1300+ object paths.
$(PROG): $(OBJ)
	@echo "$(MSG_PREFIX)Linking native ABC through response file"
	$(file >abc-link-windows.rsp,$^)
	$(VERBOSE)$(LD) -o $@ @abc-link-windows.rsp $(LDFLAGS) $(LIBS)
