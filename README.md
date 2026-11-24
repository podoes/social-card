# podoes social card

A GitHub Action that draws a branded 1280 by 640 card for a repository and keeps it up to date. The card shows the peeker, the repository name and description, and live numbers: stars, forks, open issues, contributors and the latest release.

## Options

| Input | Default | What it does |
|---|---|---|
| `output` | `.github/social-card.png` | Where the PNG is written |
| `stats` | `true` | `false` draws the static version without numbers |
| `title` | repository name | Text to show as the name |
| `description` | repository description | Text to show under the name |
| `commit` | `true` | `false` leaves the file uncommitted, for your own commit step |
| `commit-message` | `chore: update social card` | Message of the commit |

The action sets the output `changed` to `true` when the card is different from the one in the repository.

## Run it on your own machine

```sh
pip install fonttools
sudo apt install librsvg2-bin
python3 generate.py --repo podoes/podkit --out card.png
```

Set `GITHUB_TOKEN` for private repositories or to avoid rate limits. `--data file.json` skips the API and reads the values from a file, which is handy for trying out a design change.

## Fonts

Sora and Inter are bundled under the SIL Open Font License. The licence texts are in the `fonts` folder.
