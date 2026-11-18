#!/usr/bin/env python3
"""Exercise helpers/pgp.sh against a throwaway keyring under Bash and Zsh.

Keys are generated without passphrases in a temporary GNUPGHOME (kept under
/tmp because gpg-agent socket paths are length-limited). The owner's keyring,
agent and password store are never touched.
"""
import os
from pathlib import Path
import shutil
import subprocess as sp
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PGP = ROOT / 'helpers' / 'pgp.sh'
BASH = os.environ.get('SHELL_KIT_TEST_BASH', '/bin/bash')
FAILS = []


def gpg(env, *args, data=None):
    return sp.run(['gpg', '--batch', *args], env=env, input=data, text=True, capture_output=True)


def fpr_of(env, uid):
    out = gpg(env, '--with-colons', '--list-keys', uid).stdout.splitlines()
    return next(line.split(':')[9] for line in out if line.startswith('fpr:'))


def make_key(env, uid):
    gpg(env, '--passphrase', '', '--quick-gen-key', uid, 'ed25519', 'cert,sign', '1y')
    fpr = fpr_of(env, uid)
    gpg(env, '--passphrase', '', '--quick-add-key', fpr, 'cv25519', 'encr', '1y')
    return fpr


def check(name, cond, detail=''):
    if not cond:
        FAILS.append(f'{name}: {detail}')
    print(('ok   ' if cond else 'FAIL ') + name, flush=True)


def main():
    if not shutil.which('gpg'):
        print('skip: gpg not installed')
        return 0
    shells = [('bash', BASH)] + ([('zsh', shutil.which('zsh'))] if shutil.which('zsh') else [])
    tmp = tempfile.mkdtemp(prefix='skpgp.', dir='/tmp')
    try:
        home = Path(tmp)
        gh = home / 'g'
        gh.mkdir(mode=0o700)
        env = dict(os.environ, HOME=str(home), GNUPGHOME=str(gh), LC_ALL='C')
        for k in ('PGP_IDENTITY', 'PGP_IDENTITIES', 'PASSWORD_STORE_DIR', 'GPG_TTY'):
            env.pop(k, None)
        me = make_key(env, 'Real Person <real@example.test>')
        anon = make_key(env, 'Pen Name <pen@example.test>')
        (gh / 'gpg.conf').write_text(f'encrypt-to {me}\nauto-key-retrieve\n')
        (home / 'scratch').mkdir()
        env['TMPDIR'] = str(home / 'scratch')
        gpg(env, '--quick-set-expire', anon, '0')
        # A third party lives in its own keyring so we can import it uncertified.
        other_home = home / 'o'
        other_home.mkdir(mode=0o700)
        oenv = dict(env, GNUPGHOME=str(other_home))
        other = make_key(oenv, 'Other Party <other@example.test>')
        gpg(env, '--import', data=gpg(oenv, '--armor', '--export', other).stdout)
        (home / 'msg').write_text('line one\nback\\slash \\n literal\n')
        store = home / '.password-store'
        store.mkdir()
        (store / '.gpg-id').write_text(anon + '\n')
        idents = f'me={me} anon={anon}'

        for label, sh in shells:
            def run(script, stdin=''):
                body = f'. "{PGP}"\nPGP_IDENTITIES="{idents}"\n{script}'
                return sp.run([sh, '-i', '-c', body], env=env, cwd=home, input=stdin,
                              text=True, capture_output=True, timeout=60)

            # Ownertrust is the failure that broke `pass insert`: marginal own key.
            gpg(env, '--import-ownertrust', data=f'{anon}:4:\n')
            r = run('pgp doctor')
            check(f'{label}: doctor flags non-ultimate ownertrust',
                  r.returncode != 0 and 'pgp trust ' + anon in r.stdout, r.stdout + r.stderr)
            check(f'{label}: doctor flags pass recipient', f'cannot encrypt to {anon}' in r.stdout, r.stdout)
            r = run('pgp trust anon && pgp doctor')
            check(f'{label}: trust fixes doctor', r.returncode == 0 and f'can encrypt to {anon}' in r.stdout,
                  r.stdout + r.stderr)

            r = run('pgp use nobody; echo "rc=$? id=${PGP_IDENTITY-unset}"')
            check(f'{label}: use rejects unknown identity', 'id=unset' in r.stdout and 'rc=0' not in r.stdout,
                  r.stdout + r.stderr)
            r = run('pgp use anon && pgp use')
            check(f'{label}: use sets identity', r.stdout.strip().endswith('anon'), r.stdout + r.stderr)
            r = run('pgp use anon && pgp ids')
            check(f'{label}: ids marks active', f'* anon     {anon}  exp never' in r.stdout, r.stdout + r.stderr)

            # Signing follows the active identity, not gpg's default (first) key.
            r = run('pgp use anon && pgp sign -o signed.asc msg')
            st = gpg(env, '--status-fd', '1', '--verify', str(home / 'signed.asc'))
            check(f'{label}: sign uses active identity', f'VALIDSIG {anon}' in st.stdout, r.stderr + st.stdout)
            r = run('pgp use anon && pgp sign -u me -d -o msg.asc msg && pgp verify msg.asc msg')
            check(f'{label}: -u overrides, detached verify', r.returncode == 0 and 'Real Person' in r.stderr,
                  r.stderr)

            # Encrypting as anon must never reveal the real key as a recipient.
            r = run('pgp use anon && pgp encrypt -r other@example.test --trust-anyway -o out.asc msg')
            pk = gpg(env, '--list-packets', '--list-only', str(home / 'out.asc'))
            ids = {l.split('keyid ')[1].split()[0] for l in pk.stdout.splitlines() if 'keyid' in l}
            subs = lambda f: {l.split(':')[4] for l in gpg(env, '--with-colons', '--list-keys', f).stdout.splitlines()
                              if l.startswith('sub:')}
            check(f'{label}: recipients are other + self only',
                  r.returncode == 0 and ids == subs(other) | subs(anon), f'{ids} {r.stderr}')
            r = run('pgp decrypt out.asc')
            check(f'{label}: decrypt round-trips backslashes', r.stdout == (home / 'msg').read_text(),
                  repr(r.stdout) + r.stderr)
            r = run('pgp encrypt -u anon -r other@example.test -o x.asc msg')
            check(f'{label}: uncertified recipient refused', r.returncode != 0 and 'not certified' in r.stderr,
                  r.stderr)
            r = run('pgp encrypt -u anon --hide -o h.asc msg')
            pk = gpg(env, '--list-packets', '--list-only', str(home / 'h.asc'))
            check(f'{label}: --hide throws key IDs', 'keyid 0000000000000000' in pk.stdout, pk.stdout)
            r = run('pgp encrypt -u anon', stdin='piped\n')
            check(f'{label}: stdin encrypt to self', '-----BEGIN PGP MESSAGE-----' in r.stdout, r.stderr)

            r = run('pgp export -u anon')
            check(f'{label}: export public only', 'PUBLIC KEY BLOCK' in r.stdout and 'PRIVATE' not in r.stdout,
                  r.stderr)

            # Missing signer key, no tty to ask: fail clearly instead of hanging.
            sigd = gpg(oenv, '--clearsign', data='from other\n').stdout
            r = sp.run([sh, '-i', '-c', f'. "{PGP}"; pgp verify'], env=dict(env, GNUPGHOME=str(gh)),
                       input=sigd.replace('from other', 'from other'), text=True, capture_output=True,
                       timeout=60, start_new_session=True)
            # 'other' was imported above, so this must verify.
            check(f'{label}: verify pasted clearsign', r.returncode == 0, r.stderr)
            stranger = home / 's'
            stranger.mkdir(mode=0o700, exist_ok=True)
            senv = dict(env, GNUPGHOME=str(stranger))
            make_key(senv, 'Stranger <s@example.test>')
            sigs = gpg(senv, '--clearsign', data='hello\n').stdout
            r = sp.run([sh, '-i', '-c', f'. "{PGP}"; pgp verify'], env=env, input=sigs, text=True,
                       capture_output=True, timeout=60, start_new_session=True)
            check(f'{label}: missing key reported, no hang',
                  r.returncode != 0 and 'not in your keyring' in r.stderr, r.stderr)
            check(f'{label}: temporary files removed', not list((home / 'scratch').iterdir()))
    finally:
        sp.run(['gpgconf', '--kill', 'all'], env=dict(os.environ, GNUPGHOME=str(Path(tmp) / 'g')))
        for sub in ('o', 's'):
            sp.run(['gpgconf', '--kill', 'all'], env=dict(os.environ, GNUPGHOME=str(Path(tmp) / sub)))
        shutil.rmtree(tmp, ignore_errors=True)
    if FAILS:
        print('\n'.join(['', 'Failures:', *FAILS]), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
