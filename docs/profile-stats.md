# My profile stats

My cards are generated directly from GitHub's API, rather than a public stats
service that cannot read my private repositories. SVGs are stored in this profile
repository and selected for GitHub's light or dark theme. The animated greeting
has a transparent background, so it blends with either theme without a solid box.

## What is counted

- Repository and star totals include all my **owned public and private repositories**,
  including archived repositories and forks. Language totals use GitHub's language
  byte counts across those repositories' default branches. They are not percentages
  of time spent or a proficiency score, and can include documentation/scaffolding.
- Authored commits count commits linked to my GitHub account on default branches.
  Both all-time and trailing-365-day totals are shown. Unmerged branches and commits
  made with an email not linked to my account are not represented in that metric.
  A commit appearing in multiple owned repositories is counted once per repository.
- The trailing-year contributions total uses GitHub's contribution calendar,
  including private/restricted activity that GitHub reports for my account. Its
  eligibility rules differ from raw Git history, so the two totals can differ.
- Skills are based on detected committed languages and dependency/configuration
  manifests. Primary languages and recognized frameworks/tools are displayed;
  this is evidence of repository usage, not a claim of mastery in every language.

Only combined totals, language byte totals, and technology labels are published.
Private repository names, descriptions, URLs, source files, commit messages,
authors' emails, and credentials are never written to the public output. Manifest
contents are inspected in memory only. The script prints safe aggregate status.

## Enable automatic updates

The initial cards already include my private repositories. Daily refreshes and the
manual **Update public and private profile stats** workflow need a dedicated secret:

1. In [GitHub token settings](https://github.com/settings/personal-access-tokens),
   create a **fine-grained personal access token** owned by `ArshaFazlollahi` with
   an expiration. Select all my repositories (including private ones) so future
   projects are included. Grant **Contents: read-only**; **Metadata: read-only**
   is automatically included. No write permission is needed on this token.
2. In this repository's **Settings → Secrets and variables → Actions**, add a
   repository secret named **`PROFILE_READ_TOKEN`** with that token. Do not put it
   in README, source code, a URL, or a Git commit, and do not send it in chat.
3. Open **Actions → Update public and private profile stats → Run workflow**.
   Check that the workflow passes. Cards then refresh daily around 06:23 UTC.
   GitHub can delay scheduled runs or disable schedules after inactivity.
4. Renew the secret when its token expires. If my private-repository count changes
   below six, update `PROFILE_MIN_PRIVATE_REPOS` in the workflow after reviewing
   whether access is complete. The guard avoids silently publishing public-only
   figures when a token has insufficient access.

The workflow's built-in `GITHUB_TOKEN` only pushes generated files to this profile;
it cannot read all my other private repositories. The read token is passed only
to my generator, not to a third-party stats host. API errors or missing credentials
fail the workflow while retaining the last valid combined cards; there is no
public-only fallback masquerading as complete coverage.

To refresh locally, set `PROFILE_READ_TOKEN` in the process environment and run
`python scripts/update_profile.py`. Python 3.11+ and its standard library suffice.
No extra package install, paid hosting, or payment method is needed.

References: [GitHub language API](https://docs.github.com/en/rest/repos/repos#list-repository-languages),
[fine-grained tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens),
[Actions secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).
