# DeckOps

<p align="center">
  <img src="assets/images/DeckOps-banner.png" alt="DeckOps - CombatOnDeck" width="460"/>
</p>

<p align="center">
  Bringing the golden era of FPS to your Steam Deck, no terminal required.
</p>

---

DeckOps automates the installation of iw4x, CoD4x, IW3SP-MOD, and Plutonium on Steam Deck. Pick your games, hit install, and launch them straight from Steam like any other game.

---

## 💾 Installation & Uninstall

1. Press the Steam button → **Power** → **Switch to Desktop**

2. Download the **[DeckOps file](https://github.com/GalvarinoDev/DeckOps/releases/download/v1/DeckOps.desktop.download)** from this page

3. Right-click the file → **Properties** → **Permissions** → tick **"Is executable"** → OK

4. Double-click it
   - **First time:** DeckOps installs automatically
   - **Already installed:** A menu appears - choose to Launch, Reinstall, or Uninstall

> Your Steam games are never touched. Only the files DeckOps created are removed during uninstall.

---

## Requirements

- Steam Deck running SteamOS
- Each game installed through Steam and launched at least once in both SP and MP modes before running DeckOps
- Plutonium games require a free account at [plutonium.pw](https://plutonium.pw)

> Skipping the first-launch step is the #1 cause of install failures. It creates the Proton prefix and starts shader cache downloads.

---

## How It Works

DeckOps is a setup and management tool, not a launcher. Once your games are set up, launch them directly from Steam's Game Mode. Open DeckOps whenever you want to update a client, reinstall after a Steam update, add a new game, or re-apply controller templates.

For CoD4 and World at War, DeckOps creates separate non-Steam shortcuts for multiplayer modes with their own artwork and controller profiles. The original Steam games default to singleplayer.

---

## 🎮 Supported Games

DeckOps installs four controller templates into Steam during setup - two gyro layouts (Hold or Toggle) and two additional layouts for games that need them. Steam Input is enabled automatically for every supported game. You can re-apply templates anytime from **DeckOps → Settings**.

| Game | Client | Deck Model | Modes | Controller | Aim Assist | Gyro |
|---|---|---|---|---|---|---|
| Modern Warfare 1 - Campaign | IW3SP-MOD | LCD + OLED | SP | ✅ | ✅ | ✅ |
| Modern Warfare 1 - Multiplayer | CoD4x | LCD + OLED | MP | ✅ | ❌ | ✅ |
| Modern Warfare 2 - Campaign | via Steam | LCD + OLED | SP | ✅ | ❌ | ✅ |
| Modern Warfare 2 - Multiplayer | iw4x | LCD + OLED | MP | ✅ | ✅ | ✅ |
| Modern Warfare 3 - Campaign | via Steam | LCD + OLED | SP | ✅ | ❌ | ✅ |
| Modern Warfare 3 - Multiplayer | Plutonium | OLED only | MP | ✅ | ✅ | ✅ |
| World at War | Plutonium | OLED only | SP / MP / ZM | ✅ | ✅ | ✅ |
| Black Ops | Plutonium | OLED only | SP / MP / ZM | ✅ | ✅ | ✅ |
| Black Ops II - Campaign | via Steam | LCD + OLED | SP | ✅ | ❌ | ✅ |
| Black Ops II - Multiplayer & Zombies | Plutonium | OLED only | MP / ZM | ✅ | ✅ | ✅ |

> A legitimate Steam copy of each game is required. DeckOps does not provide or distribute game files.

> Gyro is implemented via Steam Input and works on all titles regardless of native client support.

### 📟 Steam Deck LCD - Plutonium Offline Play

Plutonium's dedicated servers are only stable on Steam Deck OLED. LCD users wanting Plutonium's improved campaigns or offline Zombies should check out **[PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher)** by framilano.

---

## Credits

DeckOps is an installer. The projects below are what actually make it work.

**[PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher)** - framilano's project was the original inspiration for DeckOps.

**[Plutonium](https://plutonium.pw)** - MW3, World at War, Black Ops, Black Ops II. Community client with dedicated servers, mod support, and anti-cheat. 💰 [Donate](https://forum.plutonium.pw/donate)

**[iw4x](https://iw4x.io)** - Modern Warfare 2. Community client with dedicated servers and mod support. [GitHub](https://github.com/iw4x)

**[CoD4x](https://cod4x.ovh)** - Call of Duty 4. Community client with dedicated servers and mod support. [GitHub](https://github.com/callofduty4x)

**[IW3SP-MOD](https://gitea.com/JerryALT/iw3sp_mod)** - Call of Duty 4 Campaign. Mod by JerryALT bringing gamepad support, aim assist, achievements, and Workshop mod support. [Gitea](https://gitea.com/JerryALT/iw3sp_mod)

Steam library artwork sourced from [SteamGridDB](https://www.steamgriddb.com) - thanks to Moohoo, jarvis, Ramjez, Over, Uravity-PRO, and Maxine.

**[Claude](https://claude.ai)** by Anthropic - assisted in the development of DeckOps.

---

DeckOps takes no money and has no affiliation with any of the above projects. All client software is downloaded directly from each project's official sources at install time.

---

## License

[MIT License](LICENSE)

DeckOps is not affiliated with Activision, Infinity Ward, Treyarch, or Valve. All trademarks belong to their respective owners. Use of community clients may violate the terms of service of the original games. Use at your own discretion.
