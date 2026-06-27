#!/bin/sh
# Build the `shorten` ENCODER as a black-box test-fixture generator + oracle.
# (We compile/run it; we NEVER read its .c/.h source — clean-room rule. shorten's
# license is non-FOSS, so this stays strictly black-box: it only generates .shn
# test files and serves as a second decode oracle via `shorten -x`.)
#
# Source: Tony Robinson's canonical repo (drtonyr/shorten, v2.3a, 1999),
# downloaded earlier to ~/local/scr/shorten-src/shorten-master.tar.gz
#
# The 1999 error module exit.c uses K&R <varargs.h>/va_dcl, which modern GCC
# removed. exit.c is error-reporting *utility* code, not the compression
# algorithm, so we drop it and link a modern stdarg replacement (exit_shim.c) —
# the same pattern build_w_decode.sh uses for its glibc errno shim. We patch the
# BUILD, never the algorithm, and never read shorten's source.
#
# Usage:  sh oracles/build_shorten.sh
# Result: oracles/shorten   (gitignored, Syncthing-synced like the other oracles)

set -e
SRC="$HOME/local/scr/shorten-src"
TARBALL="$SRC/shorten-master.tar.gz"
OUT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$OUT_DIR/shorten"

[ -f "$TARBALL" ] || { echo "missing $TARBALL"; exit 1; }
cd "$SRC"
tar -xzf "$TARBALL"
cd "$SRC/shorten-master"

# Modern stdarg replacement for the K&R varargs error helpers in exit.c.
# Signatures are best-effort (only hit on error paths, never on valid input).
cat > exit_shim.c <<'EOF'
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <errno.h>
#include <setjmp.h>
jmp_buf exitenv;                 /* referenced by embedded.c (library path) */
char *exitmessage;               /* error string set before longjmp (unused on valid input) */
void basic_exit(int n) { exit(n); }   /* normal termination (1 file/run) */
void error_exit(char *fmt, ...) {
    va_list a; va_start(a, fmt); vfprintf(stderr, fmt, a); va_end(a);
    exit(1);
}
void perror_exit(char *fmt, ...) {
    va_list a; va_start(a, fmt); vfprintf(stderr, fmt, a); va_end(a);
    fprintf(stderr, ": %s\n", strerror(errno)); exit(1);
}
void usage_exit(int n, char *fmt, ...) {
    va_list a; va_start(a, fmt); if (fmt) vfprintf(stderr, fmt, a); va_end(a);
    exit(n);
}
void update_exit(int n, char *fmt, ...) {
    va_list a; va_start(a, fmt); if (fmt) vfprintf(stderr, fmt, a); va_end(a);
    exit(n);
}
EOF

# -include setjmp.h: embedded.c uses jmp_buf without including it (relied on a
# transitive include in the original build). Inject it at the compiler level.
PERMISSIVE='-O2 -w -fcommon -std=gnu89 -include setjmp.h -Wno-implicit-function-declaration -Wno-implicit-int -Wno-int-conversion'

echo "=== compiling objects (skip exit.c [shimmed] and mkbshift.c [build-time gen]) ==="
OBJS=""
FAILED=""
for f in *.c; do
  case "$f" in
    exit.c|mkbshift.c|exit_shim.c) continue ;;
  esac
  if cc $PERMISSIVE -c "$f" -o "${f%.c}.o" 2>"${f%.c}.err"; then
    OBJS="$OBJS ${f%.c}.o"
  else
    echo "--- FAILED: $f ---"; tail -8 "${f%.c}.err"; FAILED="$FAILED $f"
  fi
done
cc $PERMISSIVE -c exit_shim.c -o exit.o && OBJS="$OBJS exit.o"

if [ -n "$FAILED" ]; then
  echo "OBJECTS THAT FAILED TO COMPILE:$FAILED"
fi

echo "=== linking ==="
if cc -no-pie $OBJS -lm -o shorten 2>link.err; then
  cp -f ./shorten "$OUT"
  echo "built: $OUT"
  "$OUT" -h 2>&1 | head -5 || true
else
  echo "LINK FAILED:"; tail -20 link.err
  exit 2
fi
