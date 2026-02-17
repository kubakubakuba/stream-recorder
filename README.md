# Stream recorder

A simple flask app that serves as a recorder of youtube streams.

## Installation

Install flask and toml/tomllib.

```bash
sudo pacman -S python-flask
```

## Problems

If the recording does not work, for example:
```bash
ERROR: [youtube] vytmBNhc9ig: Requested format is not available. Use --list-formats for a list of available formats
ERROR: [youtube] V7YCOMkQtMI: Sign in to confirm you’re not a bot. This helps protect our community.
```

You may need to dump your browser cookies into a file using any extension that can do that (because youtube...).

Install ytdlp-ejs to solve js challenges (if it fails on that):
```bash
sudo pacman -S yt-dlp-ejs
```

And a js runner:
```bash
curl -fsSL https://deno.land/install.sh | sh
```


To run the app as a service, modify the `recorder.service` and "install" it:

```bash
cp recorder.service /etc/systemd/system/recorder.service
sudo systemctl daemon-reload
sudo systemctl enable recorder.service
sudo systemctl start recorder.service
```

## Configuration

Create a config.toml file with the streams to record in the following format:
```toml
[[streams]]
link = "https://www.youtube.com/watch?v=vytmBNhc9ig"
at = "Tue"
start = "8:00"
end = "8:01"
name = "NASA"

[[streams]]
link = "https://www.youtube.com/watch?v=vytmBNhc9ig"
at = "Wed"
start = "8:00"
end = "8:01"
name = "NASA"
```

After every config change you should restart the service:
```bash
sudo systemctl restart recorder.service
```

