# git · see the state, then change it

**F5** toggle this sheet · F1 tmux · F2 vim · F3 grep · F4 aliases\
Read `status` and `diff` before every commit. Check the branch you are on.

## Reach first

```sh
git status -sb          # short status + branch and ahead/behind counts
git diff                # unstaged changes
git diff --staged       # what a commit would actually record
git add -p              # stage by hunk; review as you go
git commit              # opens $EDITOR for the message
git push                # send the current branch
git pull --ff-only      # refuse a surprise merge commit
git log --oneline -10   # recent history, one line each
```

`-sb` is the fastest orientation: branch, tracking, and every changed path.

## See what changed

```sh
git diff --stat                 # files and +/- counts, no content
git diff main...HEAD            # your work only, ignoring main's new commits
git diff HEAD~1 -- path/to/file # one file, against the previous commit
git show HEAD                   # the last commit, message and patch
git log -p -- path/to/file      # every change to one file
git log --oneline --graph --all # branch topology
```

Two dots compare endpoints; three dots compare against the merge base.\
`--` separates paths from revisions when a name could be either.

## Branches

```sh
git switch main                 # change branch
git switch -c feature/thing     # create and change
git switch -                    # back to the previous branch
git branch -vv                  # local branches, tracking and last commit
git branch -d old-branch        # delete; refuses if unmerged
git fetch --prune               # update remotes, drop deleted ones
```

`switch` and `restore` replace the overloaded `checkout`; both still work.

## Undo, in increasing severity

```sh
git restore path                # discard unstaged changes to a file
git restore --staged path       # unstage, keep the edit
git commit --amend              # rewrite the last commit
git revert <sha>                # new commit undoing an old one
git reset --soft HEAD~1         # undo the commit, keep changes staged
git reset --hard <sha>          # DISCARDS working tree; no undo
```

`revert` is the safe choice on anything already pushed. Before any `--hard`,
run `git stash` or note the sha from `git log`, so there is a way back.

## Recover from a mistake

```sh
git reflog                      # every HEAD position, including "lost" ones
git reset --hard HEAD@{2}       # return to where you were two moves ago
git restore --source=<sha> path # one file, as of that commit
```

Reflog keeps unreferenced commits for about 90 days: a bad reset is
usually recoverable. [Official reference](https://git-scm.com/docs)

## Stash

```sh
git stash push -m 'wip: parser' # set aside tracked changes
git stash push -u               # include untracked files
git stash list                  # what is set aside
git stash pop                   # reapply the newest and drop it
git stash apply stash@{1}       # reapply an older one, keep it
```

## Find the commit that did it

```sh
git log -S 'functionName'       # commits that added or removed that text
git log -G 'regex'              # commits whose diff matches a pattern
git blame -- path/to/file       # last commit to touch each line
git blame -L 40,60 -- file      # only those lines
```

`-S` counts occurrences, `-G` matches the patch text; `-S` is usually what
you want when hunting where something appeared or vanished.

## Before you push

```sh
git log --oneline origin/main..HEAD   # what you are about to send
git diff origin/main...HEAD           # the whole change, as reviewed
git push --force-with-lease           # safer force; see the note below
```

Never plain `--force` on a shared branch. `--force-with-lease` aborts if
someone else pushed since your last fetch.
