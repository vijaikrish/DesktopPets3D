# Putting DesktopPets3D on GitHub

This folder is ready to be a GitHub repository: source, documentation, licence files, `.gitignore` and the build
workflow are in place. A local git repository has been prepared (`git init`, files staged), but **nothing has been
committed or uploaded** - that is your step.

## Before you publish (5-minute checklist)

1. **The bird model's licence.** The 3D model was generated with Meshy (meshy.ai) and then rigged and animated.
   Meshy's terms: Free-plan models are licensed CC BY 4.0 (sharing allowed, Meshy must be credited); on a paid plan
   you own the model. [pets/sun_conure/ASSETS.md](../pets/sun_conure/ASSETS.md) and the README carry the credit
   "Model created with Meshy - CC BY 4.0 License", which satisfies both cases. The reference image the model was
   generated from must be your own (or one you may use).
2. **Code licence.** `LICENSE` is MIT (permissive: anyone may use, change and share the code with the copyright
   notice). Change it now if you prefer another licence.
3. **Sound credits** are in `pets/sun_conure/sounds/CREDITS.md` and must stay with the sounds (two are CC BY).
4. **Personal data:** none is in this folder. The bird's memory and your settings live in your user data folder, not
   here. `.gitignore` also keeps `.venv/`, `build/`, `dist/` and `release/` out of git.

## Option 1 - GitHub Desktop (easiest)

1. Install GitHub Desktop (<https://desktop.github.com>) and sign in.
2. **File > Add local repository...** > choose this folder. It is already a git repository.
3. Write a summary such as `DesktopPets3D 0.4.0` and click **Commit to main**.
4. Click **Publish repository**. Choose the name (e.g. `DesktopPets3D`), keep **"Keep this code private"** ticked
   until the checklist above is done, and click **Publish**.

## Option 2 - command line

Create an empty repository on github.com (no README, no .gitignore, no licence - this folder has them), then in this
folder:

```bash
git commit -m "DesktopPets3D 0.4.0"
git remote add origin https://github.com/<your-user>/DesktopPets3D.git
git push -u origin main
```

(The first commit needs your git identity once: `git config --global user.name "Your Name"` and
`git config --global user.email "you@example.com"` - GitHub can give you a private no-reply address under
Settings > Emails.)

Do **not** use the "upload files" page of the GitHub website: it refuses files over 25 MB, and the two bird models
are about 30 MB each. Git and GitHub Desktop handle them fine (GitHub's limit is 100 MB per file; Git LFS is not
needed).

## Make a release (the downloadable apps)

1. On GitHub: **Actions** - if asked, click "I understand my workflows, go ahead and enable them".
2. Create a version tag and push it:
   - GitHub Desktop: History > right-click the latest commit > **Create Tag...** > `v0.4.0` > then **Push origin**.
   - Command line: `git tag v0.4.0` and `git push origin v0.4.0`.
3. The **build** workflow starts (Actions tab, about 10-15 minutes). It tests, builds the Windows and macOS apps and
   creates the release **v0.4.0** with `DesktopPets3D-windows-x64.zip` and `DesktopPets3D-macos-arm64.zip` attached.
4. Open **Releases > v0.4.0 > Edit**, paste the 0.4.0 section of `CHANGELOG.md` as the description, and save.

A Windows build made on this PC is also in the `release/` folder (`DesktopPets3D-windows-x64.zip`, ignored by git).
You can drag it onto the release page by hand (**Edit > Attach binaries**) if you do not want to wait for the workflow.

## Later changes

Edit, test (`python -m unittest discover -s tests`), commit, push. For a new downloadable version: raise
`__version__` in `app/__init__.py`, add a `CHANGELOG.md` entry, commit, and push a new tag (`v0.4.1`).
