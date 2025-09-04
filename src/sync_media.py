#!/usr/bin/env python3

"""Stage media and store it on Akamai's servers"""

from argparse import ArgumentParser
from datetime import datetime
from functools import cached_property
from json import loads
from logging import basicConfig, getLogger
from os import chdir, environ
from pathlib import Path
from shutil import rmtree
from subprocess import run
from sys import stderr
from PIL import Image

# Force processing to take place in the right location.
chdir(Path(__file__).resolve().parent)


class Control:
    """Top-level processing control object"""

    IMAGE_WIDTHS = 571, 750
    JPEG_QUALITY = 80
    KEYS = "SSH_AUTH_SOCK", "SSH_AGENT_PID"
    FMT = "%(asctime)s [%(levelname)s] %(message)s"
    LOG = "sync-media.log"

    def run(self):
        """Top-level entry point for script"""

        start = datetime.now()
        if not self.staged:
            self.stage()
        self.sync()
        if not self.staged:
            elapsed = datetime.now() - start
            self.logger.info("processed %d files in %s", self.count, elapsed)
            if self.verbose:
                stderr.write(f"total processing time: {elapsed}\n")

    def stage(self):
        """Populate the source area for the sync"""

        start = datetime.now()
        opts = {"quality": self.JPEG_QUALITY}
        for path in self.blobs.glob("*"):
            doc_id = int(path.stem)
            if path.suffix == ".mp3":
                newpath = self.audio / f"{doc_id:d}.mp3"
                newpath.hardlink_to(path)
            else:
                image = Image.open(path)
                if image.mode == "P":
                    image = image.convert("RGB")
                newpath = self.images / f"{doc_id:d}.jpg"
                image.save(newpath, "JPEG", **opts)
                ratio = image.height / image.width
                for width in self.IMAGE_WIDTHS:
                    newpath = self.images / f"{doc_id:d}-{width:d}.jpg"
                    if width < image.width:
                        height = int(round(width * ratio))
                        size = width, height
                        # pylint: disable=no-member
                        scaled_image = image.resize(size, Image.LANCZOS)
                    else:
                        scaled_image = image
                    scaled_image.save(newpath, "JPEG", **opts)
            self.count += 1
            if self.verbose:
                stderr.write(f"\rstaged {self.count} files ... ")
        elapsed = datetime.now() - start
        self.logger.info("staged %d files in %s", self.count, elapsed)
        if self.verbose:
            stderr.write(f"done in {elapsed}\n")

    def sync(self):
        """Push new/change media files to Akamai"""

        self.logger.info("syncing with %s", self.host)
        if self.verbose:
            stderr.write(f"syncing with {self.host} ... ")
            # Python sometimes buffers stderr, just for jokes.
            stderr.flush()
        start = datetime.now()
        self.__start_ssh_agent()
        self.__add_key_to_agent()
        run(self.rsync, check=True)
        elapsed = datetime.now() - start
        self.logger.info("synced %d files in %s", self.count, elapsed)
        if self.verbose:
            stderr.write(f"done in {elapsed}\n")

    @cached_property
    def akamai(self):
        """Top-level directory for the staging area"""

        akamai = Path("../akamai")
        if akamai.exists():
            rmtree(akamai)
        return akamai

    @cached_property
    def audio(self):
        """Directory in which we stage the audio files"""

        audio = self.akamai / "audio"
        audio.mkdir(parents=True)
        return audio

    @cached_property
    def blobs(self):
        """Directory in which the original source media is stored"""
        return Path("../blobs")

    @cached_property
    def checksums(self):
        """If true, use checksums to determine which files need to be sent"""
        return self.opts.checksums

    @cached_property
    def count(self):  # pylint: disable=method-hidden
        """Keep track of the number of files we process

        pylint bug (https://github.com/pylint-dev/pylint/issues/8753)
        """
        return 0

    @cached_property
    def host(self):
        """Name of Akamai host"""
        return self.opts.host

    @cached_property
    def images(self):
        """Directory in which we stage the image files"""

        images = self.akamai / "images"
        images.mkdir(parents=True)
        return images

    @cached_property
    def key_data(self):
        """SSH private key used to connect with Akamai"""

        key = environ.get("AKAMAI_KEY")
        if not key:
            fallback = Path(".secrets.json")
            if fallback.exists():
                secrets = loads(fallback.read_text(encoding="utf-8"))
                key = secrets.get("AKAMAI_KEY")
        if not key:
            raise RuntimeError("missing SSH key")
        return key

    @cached_property
    def logger(self):
        """Used to record what we do"""

        logger = getLogger("media_loader")
        basicConfig(filename=self.LOG, level="INFO", format=self.FMT)
        return logger

    @cached_property
    def opts(self):
        """Runtime options specified on the command line"""

        parser = ArgumentParser()
        parser.add_argument("--host", required=True)
        parser.add_argument("--checksums", action="store_true")
        parser.add_argument("--staged", action="store_true")
        parser.add_argument("--verbose", action="store_true")
        return parser.parse_args()

    @cached_property
    def rsync(self):
        """Tuple of values used to invoke rsync with checksum comparison"""

        local, remote = "../akamai/", f"sshacs@{self.host}:media"
        check = "--checksum" if self.checksums else "--size-only"
        return "rsync", "--delete", check, "-aze", "ssh", local, remote

    @cached_property
    def staged(self):
        """If true, the staging step has already been taken care of"""
        return self.opts.staged

    @cached_property
    def verbose(self):
        """If true, show progress/errors on the console"""
        return self.opts.verbose

    def __add_key_to_agent(self):
        """Add our credentials"""

        proc = run(
            ["ssh-add", "-"],
            input=self.key_data,
            capture_output=True,
            text=True,
            check=False,
        )
        output = (proc.stdout.strip() + "\n" + proc.stderr.strip()).strip()
        if proc.returncode != 0:
            self.logger.error("failure adding SSH key to agent: %s", output)
            raise RuntimeError("failure adding SSH key to agent")
        if output:
            self.logger.info("ssh-add output: %s", output)

    def __start_ssh_agent(self):
        """Start the agent that will support authorization of our connection"""

        result = run(["ssh-agent", "-s"], capture_output=True, text=True, check=False)
        for line in result.stdout.splitlines():
            for key in self.KEYS:
                if line.startswith(key):
                    environ[key] = line.split(";")[0].split("=")[1]


if __name__ == "__main__":
    control = Control()
    try:
        control.run()
    except Exception as e:  # pylint: disable=broad-exception-caught
        control.logger.exception("sync failed")
        if control.verbose:
            stderr.write(f"\nsync failed: {e}\n")
