# Media For Akamai

This repository contains the original media files from the old CDR system, which is being retired. It also contains the software for staging those media files and syncing them with our Akamai server. Part of the staging step involves creating compressed copies of the image files (which are sent to Akamai in lieu of the originals), as well as two lower resolution copies of each file (the original resolution is used whenever that resolution is smaller than the proposed "lower" resolution). The audio (MP3) files are hard linked into the staging area.

## Options

The `--host` option is required, identifying the DNS name of the target Akamai server.

For local testing you can also use:
- `--checksums` - compare files between local and remote by calculating checksums on each end
- `--staged` - indicates that the `akamai` directory has already been populated with the files to send
- `--verbose` - causes progress to be written to the console

## Credentials

When running in a GitHub Action, you must set the `AKAMAI_KEY` secret to the string for the private SSH key used for connecting with the specified Akamai server. When running locally you must provide a file named `.secrets.json` in the `src` directory containing the JSON serialization of a dictionary containing that private key string indexed by "AKAMAI_KEY". For example:

```json
{
  "AKAMAI_KEY": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n----END OPENSSH PRIVATE KEY-----\n"
}
```