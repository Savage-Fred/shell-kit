# shellcheck shell=bash
# pgp: one command for everyday OpenPGP work with named identities.
# Sourced by integrations/shell.sh (helpers component). Bash 3.2+ and Zsh.
#
#   PGP_IDENTITIES='me=<fingerprint> anon=<fingerprint>'   # names -> key specs
#   PGP_IDENTITY=me                                        # default identity
#
# Every sign/encrypt passes the chosen key to gpg explicitly, so gpg.conf's
# default-key never signs on behalf of a different identity. Run `pgp help`.
case $- in *i*) ;; *) return 0 2>/dev/null || exit 0 ;; esac
command -v gpg >/dev/null 2>&1 || return 0

# Curses/tty pinentry needs to know the terminal; pinentry-mac ignores it.
if [ -z "${GPG_TTY-}" ] && [ -t 0 ]; then
    if [ -n "${TTY-}" ]; then GPG_TTY=$TTY; else GPG_TTY=$(tty 2>/dev/null) || GPG_TTY=; fi
    [ -n "$GPG_TTY" ] && export GPG_TTY || unset GPG_TTY
fi

_sk_pgp_die() { printf 'pgp: %s\n' "$*" >&2; exit 1; }
_sk_pgp_note() { printf '%s\n' "$*" >&2; }

# Map an identity name through PGP_IDENTITIES; anything else passes through
# unchanged (fingerprint, key ID or email), so plain gpg specs always work.
_sk_pgp_spec() {
    local pair
    for pair in ${PGP_IDENTITIES-}; do
        case $pair in "$1="*) printf '%s\n' "${pair#*=}"; return 0 ;; esac
    done
    printf '%s\n' "$1"
}

# Name for a fingerprint, if PGP_IDENTITIES has one.
_sk_pgp_name_of() {
    local pair fpr
    for pair in ${PGP_IDENTITIES-}; do
        fpr=$(_sk_pgp_fpr "${pair#*=}" secret 2>/dev/null) || continue
        [ "$fpr" = "$1" ] && { printf '%s\n' "${pair%%=*}"; return 0; }
    done
    return 1
}

# Primary fingerprint for a spec; fails unless exactly one key matches.
_sk_pgp_fpr() {
    local list=--list-keys out n
    [ "${2-}" = secret ] && list=--list-secret-keys
    out=$(gpg --batch --with-colons "$list" -- "$1" 2>/dev/null |
        awk -F: '$1=="pub"||$1=="sec"{want=1;next} want&&$1=="fpr"{print $10;want=0}')
    n=$(printf '%s\n' "$out" | grep -c .)
    [ "$n" -eq 1 ] && { printf '%s\n' "$out"; return 0; }
    [ "$n" -eq 0 ] && return 1
    _sk_pgp_note "pgp: '$1' matches $n keys; use a fingerprint"
    return 2
}

# Resolve the signing identity: -u value, else PGP_IDENTITY, else empty
# (empty means gpg's default-key). Prints a fingerprint with a secret key.
_sk_pgp_signer() {
    local want=${1:-${PGP_IDENTITY-}} fpr
    [ -n "$want" ] || return 0
    fpr=$(_sk_pgp_fpr "$(_sk_pgp_spec "$want")" secret) ||
        _sk_pgp_die "no secret key for identity '$want' (see: pgp ids)"
    printf '%s\n' "$fpr"
}

_sk_pgp_confirm() {
    local answer
    [ -r /dev/tty ] || return 1
    printf '%s [y/N] ' "$1" >/dev/tty
    IFS= read -r answer </dev/tty || return 1
    case $answer in [Yy]|[Yy][Ee][Ss]) return 0 ;; esac
    return 1
}

_sk_pgp_paste_hint() {
    [ -t 0 ] && _sk_pgp_note "$1, then press Ctrl-D on an empty line."
    return 0
}

_sk_pgp_help() {
    cat <<'EOF'
pgp — OpenPGP with named identities (gpg underneath)

  pgp ids                      identities: name, fingerprint, expiry, trust
  pgp use [NAME|-]             show / set / clear the shell's active identity
  pgp keys [PATTERN]           list public keys (long IDs, fingerprints)
  pgp new 'Name <email>' [EXP] new ed25519 + cv25519 key (EXP default 3y)
  pgp export [-u ID] [--secret]   armored key of an identity
  pgp import [FILE]            import a key from FILE or paste
  pgp fetch FPR                fetch a key from keys.openpgp.org
  pgp encrypt [-u ID] [-r WHO]... [-k] [-s] [--no-self] [--hide]
              [--trust-anyway] [-o OUT] [FILE]
                               no -r: to yourself; -k: paste recipient key
  pgp decrypt [-o OUT] [FILE]
  pgp sign [-u ID] [-d] [-o OUT] [FILE]   clearsign, or -d detached .asc
  pgp verify [FILE | SIG DATA]  offers to fetch or paste a missing key
  pgp trust [ID]               mark your own key ultimately trusted
  pgp doctor                   diagnose agent, keys, trust and pass

Identities: PGP_IDENTITIES='me=FPR anon=FPR', default PGP_IDENTITY=me.
-u/-r also accept fingerprints or emails. FILE omitted = stdin/paste.
EOF
}

# One tab-separated row per secret key: fpr, validity, ownertrust, caps, expiry, first uid.
_sk_pgp_secret_rows() {
    gpg --batch --with-colons --list-secret-keys 2>/dev/null | awk -F: '
        $1=="sec" {v=$2; ot=$9; cap=$12; ex=$7; w=1; f=""; next}
        w && $1=="fpr" {f=$10; w=0}
        $1=="uid" && f!="" {printf "%s\t%s\t%s\t%s\t%s\t%s\n", f, v, ot, cap, ex, $10; f=""}'
}

_sk_pgp_day() {
    [ -n "$1" ] || { printf 'never'; return; }
    date -r "$1" +%Y-%m-%d 2>/dev/null || date -d "@$1" +%Y-%m-%d 2>/dev/null || printf '%s' "$1"
}

_sk_pgp_ids() {
    local def rows fpr v ot cap exp uid name mark tab
    tab=$(printf '\t')
    def=$(_sk_pgp_signer 2>/dev/null)
    rows=$(_sk_pgp_secret_rows)
    [ -n "$rows" ] || { _sk_pgp_note 'no secret keys (create one: pgp new)'; return 1; }
    while IFS=$tab read -r fpr v ot cap exp uid; do
        name=$(_sk_pgp_name_of "$fpr") || name=-
        mark=' '; [ "$fpr" = "$def" ] && mark='*'
        case $ot in u) ot=ultimate ;; f) ot=full ;; m) ot=marginal ;; n) ot=never ;; *) ot=unset ;; esac
        printf '%s %-8s %s  exp %-10s  trust %-8s  %s\n' "$mark" "$name" "$fpr" "$(_sk_pgp_day "$exp")" "$ot" "$uid"
    done <<EOF
$rows
EOF
    [ -n "$def" ] || _sk_pgp_note "(no active identity: gpg's default-key signs; choose one with: pgp use NAME)"
}

_sk_pgp_new() {
    local uid=${1-} exp=${2:-3y} fpr
    [ -n "$uid" ] || _sk_pgp_die "usage: pgp new 'Name <email>' [EXPIRY]"
    gpg --quick-generate-key "$uid" ed25519 cert,sign "$exp" || _sk_pgp_die 'key generation failed or was cancelled'
    fpr=$(gpg --batch --with-colons --list-secret-keys -- "=$uid" 2>/dev/null |
        awk -F: '$1=="sec"{w=1;next} w&&$1=="fpr"{f=$10;w=0} END{print f}')
    [ -n "$fpr" ] || _sk_pgp_die "created, but could not find '$uid' afterwards"
    gpg --quick-add-key "$fpr" cv25519 encr "$exp" || _sk_pgp_die "encryption subkey failed; retry: gpg --quick-add-key $fpr cv25519 encr $exp"
    printf '\nCreated %s\n  %s\n' "$uid" "$fpr"
    printf 'Revocation certificate: %s/openpgp-revocs.d/%s.rev (store it offline)\n' "${GNUPGHOME:-$HOME/.gnupg}" "$fpr"
    printf "Name it in your rc: PGP_IDENTITIES='... NAME=%s'\n" "$fpr"
}

_sk_pgp_export() {
    local who='' secret=0 fpr
    while [ $# -gt 0 ]; do
        case $1 in
            -u) [ $# -ge 2 ] || _sk_pgp_die '-u needs an identity'; who=$2; shift 2 ;;
            --secret) secret=1; shift ;;
            *) who=$1; shift ;;
        esac
    done
    if [ -n "$who" ]; then
        fpr=$(_sk_pgp_fpr "$(_sk_pgp_spec "$who")") || _sk_pgp_die "no key for '$who'"
    else
        fpr=$(_sk_pgp_signer)
        [ -n "$fpr" ] || _sk_pgp_die 'no identity: use -u ID, or set one with pgp use NAME'
    fi
    if [ "$secret" = 1 ]; then
        [ -t 1 ] && _sk_pgp_die 'refusing to print a secret key to the terminal; redirect to a file'
        gpg --armor --export-secret-keys -- "$fpr"
    else
        gpg --armor --export --export-options export-minimal -- "$fpr"
    fi
}

_sk_pgp_import() {
    if [ $# -gt 0 ]; then gpg --import -- "$@"; return; fi
    _sk_pgp_paste_hint 'Paste the public key block'
    gpg --import
}

_sk_pgp_fetch() {
    [ -n "${1-}" ] || _sk_pgp_die 'usage: pgp fetch FINGERPRINT'
    gpg --keyserver hkps://keys.openpgp.org --recv-keys -- "$1"
}

_sk_pgp_encrypt() {
    local who='' out='' sign=0 self=1 hide=0 paste=0 anyway=0 rcpts='' r spec fpr valid
    while [ $# -gt 0 ]; do
        case $1 in
            -u) [ $# -ge 2 ] || _sk_pgp_die '-u needs an identity'; who=$2; shift 2 ;;
            -r) [ $# -ge 2 ] || _sk_pgp_die '-r needs a recipient'; rcpts="$rcpts$2
"; shift 2 ;;
            -k|--paste-key) paste=1; shift ;;
            -s|--sign) sign=1; shift ;;
            --no-self) self=0; shift ;;
            --hide) hide=1; shift ;;
            --trust-anyway) anyway=1; shift ;;
            -o) [ $# -ge 2 ] || _sk_pgp_die '-o needs a path'; out=$2; shift 2 ;;
            --) shift; break ;;
            -*) _sk_pgp_die "encrypt: unknown option $1" ;;
            *) break ;;
        esac
    done
    [ $# -le 1 ] || _sk_pgp_die 'encrypt takes at most one input file'
    local me; me=$(_sk_pgp_signer "$who") || exit 1
    local tmp; tmp=$(mktemp -d "${TMPDIR:-/tmp}/pgp.XXXXXX") || _sk_pgp_die 'mktemp failed'
    trap 'rm -rf "$tmp"' EXIT
    local input=${1-}
    set -- --encrypt
    [ -n "$me" ] && set -- "$@" --local-user "$me"
    if [ "$paste" = 1 ]; then
        _sk_pgp_note "Paste the recipient's public key block, then press Ctrl-D."
        cat </dev/tty >"$tmp/rcpt.asc" 2>/dev/null || cat >"$tmp/rcpt.asc"
        [ -s "$tmp/rcpt.asc" ] || _sk_pgp_die 'no key pasted'
        gpg --batch --show-keys --with-fingerprint "$tmp/rcpt.asc" >&2 || _sk_pgp_die 'that is not a usable public key'
        set -- "$@" --recipient-file "$tmp/rcpt.asc"
    fi
    while IFS= read -r r; do
        [ -n "$r" ] || continue
        spec=$(_sk_pgp_spec "$r")
        fpr=$(_sk_pgp_fpr "$spec") || _sk_pgp_die "no public key for '$r' (pgp import / pgp fetch)"
        valid=$(gpg --batch --with-colons --list-keys -- "$fpr" 2>/dev/null | awk -F: '$1=="pub"{print $2; exit}')
        case $valid in
            f|u) ;;
            *) [ "$anyway" = 1 ] || _sk_pgp_die "'$r' ($fpr) is not certified. Check the fingerprint with its owner, then certify it (gpg --lsign-key $fpr) or rerun with --trust-anyway" ;;
        esac
        set -- "$@" --recipient "$fpr"
    done <<EOF
$rcpts
EOF
    if [ -z "$rcpts" ] && [ "$paste" = 0 ]; then
        [ -n "$me" ] || me=$(gpg --batch --with-colons --list-secret-keys 2>/dev/null | awk -F: '$1=="sec"{w=1;next} w&&$1=="fpr"{print $10;exit}')
        [ -n "$me" ] || _sk_pgp_die 'no recipient and no secret key to encrypt to'
        self=1
    fi
    if [ "$self" = 1 ]; then
        [ -n "$me" ] || _sk_pgp_die 'no active identity to add as self-recipient; pass -u ID or --no-self'
        set -- "$@" --recipient "$me"
    fi
    [ "$sign" = 1 ] && set -- "$@" --sign
    [ "$hide" = 1 ] && set -- "$@" --throw-keyids
    [ "$anyway" = 1 ] && set -- "$@" --trust-model always
    case $out in *.gpg) ;; *) set -- "$@" --armor ;; esac
    [ -n "$out" ] && set -- "$@" --yes --output "$out"
    [ -z "$input" ] && _sk_pgp_paste_hint 'Enter the message'
    if [ -n "$input" ]; then gpg "$@" -- "$input"; else gpg "$@"; fi
}

_sk_pgp_decrypt() {
    local out=''
    while [ $# -gt 0 ]; do
        case $1 in
            -o) [ $# -ge 2 ] || _sk_pgp_die '-o needs a path'; out=$2; shift 2 ;;
            --) shift; break ;;
            -*) _sk_pgp_die "decrypt: unknown option $1" ;;
            *) break ;;
        esac
    done
    [ $# -le 1 ] || _sk_pgp_die 'decrypt takes at most one input file'
    [ $# -eq 0 ] && _sk_pgp_paste_hint 'Paste the encrypted message'
    if [ -n "$out" ]; then gpg --decrypt --yes --output "$out" -- "$@"
    else gpg --decrypt -- "$@"; fi
}

_sk_pgp_sign() {
    local who='' out='' detach=0 me
    while [ $# -gt 0 ]; do
        case $1 in
            -u) [ $# -ge 2 ] || _sk_pgp_die '-u needs an identity'; who=$2; shift 2 ;;
            -d|--detach) detach=1; shift ;;
            -o) [ $# -ge 2 ] || _sk_pgp_die '-o needs a path'; out=$2; shift 2 ;;
            --) shift; break ;;
            -*) _sk_pgp_die "sign: unknown option $1" ;;
            *) break ;;
        esac
    done
    [ $# -le 1 ] || _sk_pgp_die 'sign takes at most one input file'
    me=$(_sk_pgp_signer "$who") || exit 1
    local input=${1-}
    if [ "$detach" = 1 ]; then set -- --detach-sign --armor; else set -- --clearsign; fi
    [ -n "$me" ] && set -- "$@" --local-user "$me"
    [ -n "$out" ] && set -- "$@" --yes --output "$out"
    [ -z "$input" ] && _sk_pgp_paste_hint 'Enter the message to sign'
    if [ -n "$input" ]; then gpg "$@" -- "$input"; else gpg "$@"; fi
}

_sk_pgp_verify() {
    local tmp rc missing fpr
    tmp=$(mktemp -d "${TMPDIR:-/tmp}/pgp.XXXXXX") || _sk_pgp_die 'mktemp failed'
    trap 'rm -rf "$tmp"' EXIT
    if [ $# -eq 0 ]; then
        _sk_pgp_paste_hint 'Paste the whole signed message'
        cat >"$tmp/msg"
        [ -s "$tmp/msg" ] || _sk_pgp_die 'no message provided'
        set -- "$tmp/msg"
    fi
    [ $# -le 2 ] || _sk_pgp_die 'usage: pgp verify [FILE | SIG DATA]'
    gpg --status-fd 3 --verify -- "$@" 3>"$tmp/status" && return 0
    rc=$?
    # ERRSIG field 9 carries the issuer fingerprint when the signature has one.
    missing=$(awk '$2=="NO_PUBKEY"{print $3; exit}' "$tmp/status")
    [ -n "$missing" ] || exit "$rc"
    fpr=$(awk '$2=="ERRSIG" && length($9)>=40 {print $9; exit}' "$tmp/status")
    _sk_pgp_note "The signer's key (${fpr:-$missing}) is not in your keyring."
    if [ -n "$fpr" ] && _sk_pgp_confirm 'Fetch it from keys.openpgp.org?'; then
        _sk_pgp_fetch "$fpr" || true
    elif _sk_pgp_confirm 'Paste their public key instead?'; then
        _sk_pgp_note 'Paste the public key block, then press Ctrl-D.'
        gpg --import </dev/tty || true
    else
        exit "$rc"
    fi
    gpg --verify -- "$@"
}

_sk_pgp_trust() {
    local fpr
    fpr=$(_sk_pgp_signer "${1-}") || exit 1
    [ -n "$fpr" ] || _sk_pgp_die 'usage: pgp trust ID (or set an active identity)'
    # Ultimate trust is only for keys you own; _sk_pgp_signer required the secret key.
    printf '%s:6:\n' "$fpr" | gpg --import-ownertrust && gpg --check-trustdb >/dev/null 2>&1
    gpg --list-keys --keyid-format long -- "$fpr" | sed -n '/^uid/p'
}

_sk_pgp_doctor() {
    local bad=0 home=${GNUPGHOME:-$HOME/.gnupg} line fpr v ot cap exp uid id store rows tab
    tab=$(printf '\t')
    _ok() { printf '  ok   %s\n' "$*"; }
    _bad() { printf '  FAIL %s\n' "$*"; bad=1; }
    _warn() { printf '  warn %s\n' "$*"; }
    printf 'gpg: %s (%s)\n' "$(command -v gpg)" "$(gpg --version | sed -n 1p)"
    if gpg-connect-agent /bye >/dev/null 2>&1; then _ok 'gpg-agent answers'
    else _bad 'gpg-agent does not answer (gpgconf --kill gpg-agent; it restarts on demand)'; fi
    [ -t 0 ] && { [ -n "${GPG_TTY-}" ] && _ok "GPG_TTY=$GPG_TTY" || _warn 'GPG_TTY unset (terminal pinentry cannot prompt)'; }
    line=$(sed -n 's/^[[:space:]]*default-key[[:space:]][[:space:]]*//p' "$home/gpg.conf" 2>/dev/null | tail -1)
    [ -n "$line" ] && _ok "gpg.conf default-key $line" || _warn 'no default-key in gpg.conf (gpg picks the first secret key)'
    grep -q '^[[:space:]]*auto-key-retrieve' "$home/gpg.conf" 2>/dev/null &&
        _warn 'auto-key-retrieve is on: verifying contacts keyservers automatically (pgp verify asks first)'
    printf 'secret keys:\n'
    rows=$(_sk_pgp_secret_rows)
    [ -n "$rows" ] || _bad 'no secret keys (pgp new)'
    while IFS=$tab read -r fpr v ot cap exp uid; do
        [ -n "$fpr" ] || continue
        printf ' %s %s\n' "$fpr" "$uid"
        case $ot in u) _ok 'ownertrust ultimate' ;; *) _bad "ownertrust '${ot:-unset}', not ultimate: batch encryption (pass insert) fails. Fix: pgp trust $fpr" ;; esac
        case $v in e) _bad 'expired (gpg --quick-set-expire FPR 1y)' ;; r) _bad 'revoked' ;; esac
        case $cap in *E*) ;; *) _bad "no usable encryption subkey (gpg --quick-add-key $fpr cv25519 encr 3y)" ;; esac
        case $cap in *S*) ;; *) _bad 'no usable signing key' ;; esac
        if [ -n "$exp" ] && [ "$exp" -lt $(( $(date +%s) + 30*86400 )) ]; then _warn "expires $(_sk_pgp_day "$exp")"; fi
    done <<EOF
$rows
EOF
    for line in ${PGP_IDENTITIES-}; do
        _sk_pgp_fpr "${line#*=}" secret >/dev/null 2>&1 && _ok "identity ${line%%=*}" || _bad "identity ${line%%=*}: no secret key for ${line#*=}"
    done
    [ -n "${PGP_IDENTITY-}" ] && { _sk_pgp_fpr "$(_sk_pgp_spec "$PGP_IDENTITY")" secret >/dev/null 2>&1 &&
        _ok "active identity $PGP_IDENTITY" || _bad "active identity $PGP_IDENTITY has no secret key"; }
    store=${PASSWORD_STORE_DIR:-$HOME/.password-store}
    if [ -f "$store/.gpg-id" ]; then
        printf 'pass (%s):\n' "$store"
        while IFS= read -r id; do
            [ -n "$id" ] || continue
            if printf '' | gpg --batch --yes --encrypt --recipient "$id" --output /dev/null 2>/dev/null
            then _ok "can encrypt to $id"
            else _bad "cannot encrypt to $id (pass insert will fail; see ownertrust above)"; fi
        done <"$store/.gpg-id"
    fi
    exit "$bad"
}

_sk_pgp_main() {
    [ -n "${ZSH_VERSION-}" ] && emulate -L sh
    local cmd=${1:-help}
    [ $# -gt 0 ] && shift
    case $cmd in
        ids|id|whoami) _sk_pgp_ids ;;
        keys|ls) gpg --list-keys --keyid-format long --with-fingerprint -- "$@" ;;
        new|gen) _sk_pgp_new "$@" ;;
        export) _sk_pgp_export "$@" ;;
        import) _sk_pgp_import "$@" ;;
        fetch) _sk_pgp_fetch "$@" ;;
        encrypt|enc|e) _sk_pgp_encrypt "$@" ;;
        decrypt|dec|d) _sk_pgp_decrypt "$@" ;;
        sign|s) _sk_pgp_sign "$@" ;;
        verify|v) _sk_pgp_verify "$@" ;;
        trust) _sk_pgp_trust "$@" ;;
        doctor) _sk_pgp_doctor ;;
        help|-h|--help) _sk_pgp_help ;;
        *) _sk_pgp_note "pgp: unknown command '$cmd'"; _sk_pgp_help >&2; exit 2 ;;
    esac
}

pgp() {
    if [ "${1-}" = use ]; then
        # Runs in the current shell so the selection sticks for this session.
        case ${2-} in
            '') printf '%s\n' "${PGP_IDENTITY:-(gpg default-key)}" ;;
            -) unset PGP_IDENTITY ;;
            *) ( [ -n "${ZSH_VERSION-}" ] && emulate -L sh; _sk_pgp_signer "$2" >/dev/null ) &&
                PGP_IDENTITY=$2 && export PGP_IDENTITY ;;
        esac
        return
    fi
    ( _sk_pgp_main "$@" )
}
