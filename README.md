# DeckOps

<p align="center">
  <img src="assets/images/DeckOps-banner.png" alt="DeckOps - CombatOnDeck" width="460"/>
</p>

<p align="center">
  Bringing the Golden Age of FPS to your Steam Deck, no terminal required.
</p>

---

DeckOps automates the installation of iw4x, CoD4x, IW3SP-MOD, and Plutonium on Steam Deck. Pick your games, hit install, and launch them straight from Steam like any other game.

---

## 🎮 Supported Games

| Game | Modes | Client | Deck Model | Aim Assist | Gyro |
|---|---|---|---|---|---|
| Modern Warfare 1 | SP | [IW3SP-MOD](https://gitea.com/JerryALT/iw3sp_mod) | LCD + OLED | ✅ | ✅ |
| Modern Warfare 1 | MP | [CoD4x](https://cod4x.ovh) | LCD + OLED | ❌ | ✅ |
| Modern Warfare 2 | MP | [iw4x](https://iw4x.io) | LCD + OLED | ✅ | ✅ |
| Modern Warfare 3 | MP | [Plutonium](https://plutonium.pw) | OLED only | ✅ | ✅ |
| World at War | SP/ZM + MP | [Plutonium](https://plutonium.pw) | OLED only | ✅ | ✅ |
| Black Ops | SP/ZM + MP | [Plutonium](https://plutonium.pw) | OLED only | ✅ | ✅ |
| Black Ops II | ZM + MP | [Plutonium](https://plutonium.pw) | OLED only | ✅ | ✅ |
||  |— Coming Soon —|  |  |  |
| Black Ops II | SP | [T6SP-Mod](https://github.com/Rattpak/T6SP-Mod-Release) | LCD + OLED | ✅ | ✅ |

> **Steam Deck LCD:** Plutonium online servers require OLED. For offline Campaign and Zombies on LCD, see [PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher).

> All titles support controller and gyro via Steam Input. Choose **Hold** (R5 held) or **Toggle** (R5 press) during setup. Aim assist is not available for Steam-native modes (MW2 SP, MW3 SP, BO2 SP) yet. Black Ops II uses a dedicated controller layout that does not support dual input so Gyro feels a little different from other games.

---

## ⚠️ Before You Install
Before running DeckOps, launch each game through Steam in every mode shown in the table above. This creates the Proton prefix and starts shader cache downloads. Skipping this is the most common cause of install failures.

Plutonium games require a free account at [plutonium.pw](https://plutonium.pw). 

---

## 💾 Installation & Uninstall

1. Press the Steam button -> **Power** -> **Switch to Desktop**
2. Open a browser and navigate to this GitHub page
3. Download the **[DeckOps file](https://github.com/GalvarinoDev/DeckOps/releases/download/v1/DeckOps.desktop)**
4. Right-click the file -> **Properties** -> **Permissions** -> tick **"Is executable"** -> OK
5. Double-click it
   - **First time:** DeckOps installs automatically
   - **Already installed:** A menu appears - choose to Launch, Reinstall, or Uninstall

![DeckOps demo](https://github.com/user-attachments/assets/fad3c437-137e-411c-9dee-a14f4983e1a6)
*Mock up of the install process.*

> Your Steam games are never touched. Only files created by DeckOps are removed during uninstall.

---

## ⚠️ After Installation

**DeckOps will switch you to Game Mode automatically.** The transition may take a moment — do not turn off your Steam Deck. Launch every modded game at least once before using Steam in Desktop Mode, or Steam Cloud will overwrite your setup. If asked about cloud saves choose **Keep Local**. If asked about launching in safe mode or changing your settings due to a hardware change choose **No**.

- **MW1 & WaW:** Steam will ask which mode to launch on first run. Select Singleplayer or Campaign and set it as your default. Multiplayer for these games launches via the DeckOps shortcuts in your library instead.
- **MW1 SP (IW3SP-MOD):** On first launch, the game will ask you to select a profile. Choose **Player** — this is the profile DeckOps created with your display settings. Creating a new profile will use default settings instead.
- **MW1 MP** requires two Steam launches to finish setup, then runs normally on the third.
- **BO2 SP** display settings must be set manually in-game. MP and ZM are configured automatically.
- The latest GE-Proton is downloaded and set automatically for all games.
- XACT audio is installed automatically via Protontricks for WaW, BO1 SP, and BO1 MP. Protontricks will be downloaded via Flatpak if not already present.

---

## Credits

DeckOps is an installer. This project wouldn't exist without the years of foundational work from these teams. They truly deserve all the credit:

**[CoD4x](https://cod4x.ovh)** - Modern Warfare 1 Multiplayer client. [GitHub](https://github.com/callofduty4x)

**[IW3SP-MOD](https://gitea.com/JerryALT/iw3sp_mod)** - Modern Warfare 1 Singleplayer client by [JerryALT](https://gitea.com/JerryALT).

**[iw4x](https://iw4x.io)** - Modern Warfare 2 Multiplayer client. [GitHub](https://github.com/iw4x)

**[T6SP-Mod](https://github.com/Rattpak/T6SP-Mod-Release)** - Black Ops II Singleplayer client by [Rattpak](https://github.com/Rattpak).

**[Plutonium](https://plutonium.pw)** - Modern Warfare 3, World at War, Black Ops, and Black Ops II client. 💰 [Donate](https://forum.plutonium.pw/donate)

---
**[PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher)** - Original inspiration for DeckOps.

Steam artwork from [SteamGridDB](https://www.steamgriddb.com) - thanks to [Moohoo](https://www.steamgriddb.com/profile/76561198009314736), [jarvis](https://www.steamgriddb.com/profile/76561198103947979), [Ramjez](https://www.steamgriddb.com/profile/76561198122547176), [Over](https://www.steamgriddb.com/profile/76561198049670875), [Uravity-PRO](https://www.steamgriddb.com/profile/76561198167607660), and [Maxine](https://www.steamgriddb.com/profile/76561198130550992).

**[Claude](https://claude.ai)** by Anthropic - assisted in development.

---

> DeckOps is not affiliated with Activision, Infinity Ward, Treyarch, or Valve. All trademarks belong to their respective owners. A legitimate Steam copy of each game is required. DeckOps does not provide or distribute game files.

## License

[MIT License](LICENSE)
