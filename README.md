# Madomi

A native desktop anime browser and player frontend built with Python and PySide6.

Madomi is designed as a full desktop application rather than a simple command generator. It provides a visual interface for discovering anime, browsing metadata, viewing series information, and launching playback through the ani-cli / mpv ecosystem.

If you've used **[ani-gui](https://github.com/JoaoPucci/ani-gui)** before, this is basically that but uses **[ani-cli](https://github.com/pystardust/ani-cli)** instead of 3rd party sources.

> Formerly known as AniSight.

## ⚠️ Warning

This was built on SteamOS, so there is no guarantee it'll work on other systems like **MacOS, Windows,** or **Arch.**

## ✨ Features

Madomi is still in development, but the current project includes:

- Home page with featured and trending anime
- Anime search
- Poster and banner artwork
- Anime details pages
- Episode selection
- Playback through ani-cli / mpv
- Native PySide6 / Qt interface
- Custom sidebar navigation
- History and settings sections
- Linux and SteamOS support
- AniList-powered metadata and discovery

More features are planned as development continues.

## 🛠️ Built With

- **Python**
- **PySide6 / Qt**
- **ani-cli**
- **mpv**
- **AniList data**

## 🚧 Project Status

Madomi is currently an experimental work in progress and is **not considered release-ready**.

The project is being built as a genuine graphical desktop client, with its own navigation, layouts, media views, playback flow, and visual identity.

Development may change structure, behavior, or design significantly between commits.

## 📦 Running From Source

Clone the repository:

```bash
git clone https://github.com/EpplaAlpsoni/AniSight.git
cd Madomi
```

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

Then run:

```bash
python main.py
```

Additional external dependencies such as **ani-cli** and **mpv** may be required for playback functionality.

## 🗂️ Project Structure

```text
.
├── main.py                  # Main Madomi interface
├── ani_cli_integration.py   # ani-cli integration/backend logic
├── stream_proxy.py          # Streaming support
├── madomi_mpv_capture       # mpv integration helper
├── requirements.txt
├── tests/
└── *.svg                    # Madomi UI and navigation assets
```

## 🎨 Design

Madomi uses a dark, media-focused interface built around large artwork, featured banners, compact navigation, and native Qt widgets.

The project takes inspiration from modern media applications while keeping its own visual identity.

## 💙 Credits & Inspiration

A major source of inspiration for Madomi is **[ani-gui](https://github.com/JoaoPucci/ani-gui)** by **JoaoPucci**.

## 🤝 Contributing

Madomi is still evolving quickly, so large-scale contributions may be difficult to coordinate right now.

Bug reports, suggestions, ideas, and feedback are still welcome.

## 📄 License

Madomi is licensed under the **MIT License**.

See [`LICENSE`](LICENSE) for details.

## ⚠️ Disclaimer

Madomi is an independent project and is not affiliated with or endorsed by ani-cli, AniList, mpv, ani-gui, or their contributors.

Madomi does not host anime or video content. It provides a graphical frontend that interacts with external tools and services.

Users are responsible for complying with the laws and terms applicable in their location and to the services they use.
