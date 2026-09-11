#!/usr/bin/env python3
"""Static config discovery must not execute the files it inspects."""
import os
import pty
import shutil
from pathlib import Path
import subprocess
import tempfile

BASH = os.environ.get('SHELL_KIT_TEST_BASH', '/bin/bash')

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='shell-kit-configs-') as tmp:
    home = Path(tmp)
    (home / 'parts').mkdir()
    (home / '.bashrc').write_text('''# source /not/a/config
echo "source /also/not/a/config"
echo if source /not/a/command
base="$HOME/parts"
[ -f "$base/aliases.sh" ] && source "$base/aliases.sh"
. "$HOME/space name.sh"
. "${MISSING_CONFIG_DIR:-$HOME}/fallback.sh"
source "$(touch "$HOME/EXECUTED")"
read -r value <<< "hello"
. "$HOME/after-here-string.sh"
cat <<'EOF'
source /heredoc/not/config
EOF
''')
    (home / 'parts/aliases.sh').write_text('. "$HOME/.bashrc"\n')
    (home / 'after-here-string.sh').write_text('# here-string follower\n')
    (home / 'fallback.sh').write_text('# fallback path\n')
    (home / 'space name.sh').write_text('alias hi=true\n')
    env = dict(os.environ, HOME=tmp, CONFIGS_SHELL='bash', CONFIGS_LOGIN='0')
    def run(*args):
        return subprocess.run([BASH, str(ROOT/'vanilla/configs'), *args], env=env,
                              text=True, capture_output=True, check=True).stdout
    out = run('deps', '-f', str(home/'.bashrc'))
    assert '~/parts/aliases.sh' in out and '~/space name.sh' in out and '~/fallback.sh' in out, out
    assert '~/after-here-string.sh' in out, out
    assert '[cycle]' in out and '[dynamic source' in out, out
    assert '/not/a/config' not in out and '/heredoc/not/config' not in out and '/not/a/command' not in out, out
    assert not (home/'EXECUTED').exists()
    assert '\x1b' not in out
    assert '~/.bashrc' in run()
    (home/'.bash_profile').write_text('. "$HOME/.bashrc"\n')
    env['CONFIGS_LOGIN'] = '1'
    assert '~/.bash_profile' in run()
    env.update(CONFIGS_SHELL='zsh', CONFIGS_ZDOTDIR=str(home/'zdir'))
    (home/'zdir').mkdir()
    (home/'zdir/.zshrc').write_text('. "$HOME/space name.sh"\n')
    assert '~/zdir/.zshrc' in run()
    assert '~/parts/aliases.sh' in run('deps', '-d', str(home/'parts'))
    assert '~/parts/aliases.sh' in run('deps', '-f', 'aliases.sh', '-d', str(home/'parts'))
    (home/'continuations.sh').write_text('# example command ' + chr(92) + '\n' +
                                         'source "$HOME/space name.sh"\n' +
                                         'command . "$HOME/fallback.sh"\n' +
                                         'source ' + chr(92) + '\n"$HOME/after-here-string.sh"\n')
    continued = run('deps', '-f', str(home/'continuations.sh'))
    assert '~/space name.sh' in continued and '~/fallback.sh' in continued, continued
    assert '~/after-here-string.sh' in continued, continued
    # The wrapper reports the calling shell, even if SHELL names another one.
    for shell in (BASH, shutil.which('zsh')):
        if not shell:
            continue
        shellenv = dict(env, SHELL='/bin/false', SHELL_KIT_COMPONENTS=' helpers ',
                        PATH=str(ROOT/'bin') + ':' + os.environ['PATH'])
        shellenv.pop('CONFIGS_SHELL', None)
        command = 'ZDOTDIR="$HOME/zdir"; . "' + str(ROOT/'integrations/shell.sh') + '"; configs'
        actual = subprocess.run([shell, *(['-fic'] if 'zsh' in shell else ['--noprofile', '--norc', '-ic']), command], env=shellenv,
                                text=True, capture_output=True, check=True).stdout
        assert ('~/zdir/.zshrc' if 'zsh' in shell else '~/.bashrc') in actual, actual
    # Bare source filenames follow Bash PATH order; Zsh source checks cwd first.
    (home/'parts/same').write_text('# PATH file\n')
    (home/'same').write_text('# cwd file\n')
    (home/'lookup.sh').write_text('source same\n. same\n')
    for shell in ('bash', 'zsh'):
        lookup = subprocess.run([BASH, str(ROOT/'vanilla/configs'), 'deps', '-f', str(home/'lookup.sh')],
                                cwd=home, env=dict(env, CONFIGS_SHELL=shell,
                                PATH=str(home/'parts') + ':' + os.environ['PATH']),
                                text=True, capture_output=True, check=True).stdout
        assert '~/parts/same' in lookup, lookup
        assert ('|-- ~/same ' in lookup) == (shell == 'zsh'), lookup
    (home/'dot.sh').write_text('. same\n')
    lookup = subprocess.run([BASH, str(ROOT/'vanilla/configs'), 'deps', '-f', str(home/'dot.sh')],
                            cwd=home, env=dict(env, CONFIGS_SHELL='zsh', PATH='/usr/bin:/bin'),
                            text=True, capture_output=True, check=True).stdout
    assert 'not found on PATH' in lookup and '|-- ~/same ' not in lookup, lookup
    # Terminal links encode spaces, and editor dispatch passes one literal path.
    master, slave = pty.openpty()
    try:
        subprocess.run([BASH, str(ROOT/'vanilla/configs'), 'deps', '-f', str(home/'space name.sh')],
                       env=dict(env, TERM='xterm'), stdout=slave, check=True)
        data = os.read(master, 65536)
        assert b'\x1b]8;;file://' in data and b'space%20name.sh' in data, data
    finally:
        os.close(master); os.close(slave)
    editor = home/'my editor'
    editor.write_text('#!/bin/sh\nprintf "%s" "$1" > "$HOME/opened"\n')
    editor.chmod(0o755)
    env['VISUAL'] = str(editor)
    run('open', str(home/'space name.sh'))
    assert (home/'opened').read_text() == str(home/'space name.sh')
print('configs checks passed')
