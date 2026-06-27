#!/bin/sh
# Build NIST SPHERE `w_decode` as a black-box shorten DECODE ORACLE.
# (We compile/run it; we never read its .c/.h source — clean-room rule.)
#
# w_decode is the only tool that decodes shorten type-8 (lossless mu-law) SPHERE
# files; ffmpeg cannot. Used to reverse-engineer + validate Phase C.
#
# Caveat: it has a heap-corruption bug on LARGE files (e.g. multi-minute
# CALLHOME) and aborts — fine as an oracle for the small sph2pipe test files.
#
# Usage of the built binary:
#   w_decode -f -o pcm_01 in.sph out.sph   # decode shorten -> 16-bit PCM SPHERE
#   w_decode -f -o ulaw   in.sph out.sph   # decode shorten -> mu-law SPHERE
# Strip the 1024-byte SPHERE header from out.sph to get the raw payload.

set -e
SPHERE="${1:-$HOME/local/scr/sphere}"
OUT="${2:-$(pwd)/w_decode}"

# Modern glibc removed sys_errlist/sys_nerr and made errno thread-local; the
# 1992 code references them non-TLS. Provide non-TLS stubs and allow multiple
# definition at link time. (This patches the LINK, not the source.)
TMP="$(mktemp -d)"
cat > "$TMP/errno_shim.c" <<'EOF'
int errno;
int sys_nerr = 0;
const char *sys_errlist[1] = {0};
EOF
cc -c "$TMP/errno_shim.c" -o "$TMP/errno_shim.o"

# Libraries (libsp.a, libutil.a) come prebuilt in $SPHERE/lib; run `make it`
# in $SPHERE first if they are missing.
cc -I "$SPHERE/include" -L "$SPHERE/lib" -no-pie -DNARCH_x86-64 \
   "$SPHERE/src/bin/w_decode.c" "$TMP/errno_shim.o" \
   -lsp -lutil -lm -Wl,--allow-multiple-definition -o "$OUT"
echo "built: $OUT"
