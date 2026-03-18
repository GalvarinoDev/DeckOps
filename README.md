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

| Game | Modes | Client | Deck Model | Controller | Aim Assist | Gyro | Launch First |
|---|---|---|---|---|---|---|---|
| Modern Warfare 1 | SP | IW3SP-MOD | LCD + OLED | ✅ | ✅ | ✅ | SP |
| Modern Warfare 1 | MP | CoD4x | LCD + OLED | ✅ | ❌ | ✅ | MP |
| Modern Warfare 2 | MP | iw4x | LCD + OLED | ✅ | ✅ | ✅ | MP |
| Modern Warfare 3 | MP | Plutonium | OLED only | ✅ | ✅ | ✅ | MP |
| World at War | SP / MP / ZM | Plutonium | OLED only | ✅ | ✅ | ✅ | SP + MP |
| Black Ops | SP / MP / ZM | Plutonium | OLED only | ✅ | ✅ | ✅ | SP + MP |
| Black Ops II | MP / ZM | Plutonium | OLED only | ✅ | ✅ | ✅ | MP + Zombies |

> All titles support controller and gyro via Steam Input. Choose **Hold** (R5 held) or **Toggle** (R5 press) during setup. Aim assist is not available for Steam-native modes (MW2 SP, MW3 SP, BO2 SP) yet.

> **Black Ops II MP and Zombies** use a dedicated controller layout that does not support dual input - gyro feel may differ from other titles.

> **Steam Deck LCD:** Plutonium online servers require OLED. For offline Campaign and Zombies on LCD, see [PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher).

---

## 💾 Installation & Uninstall

1. Press the Steam button -> **Power** -> **Switch to Desktop**
2. Open a browser and navigate to this GitHub page
3. Download the **[DeckOps file](https://github.com/GalvarinoDev/DeckOps/releases/download/v1/DeckOps.desktop)**
4. Right-click the file -> **Properties** -> **Permissions** -> tick **"Is executable"** -> OK
5. Double-click it
   - **First time:** DeckOps installs automatically
   - **Already installed:** A menu appears - choose to Launch, Reinstall, or Uninstall

> Your Steam games are never touched. Only files created by DeckOps are removed during uninstall.

---

## ⚠️ Before You Install

Plutonium games require a free account at [plutonium.pw](https://plutonium.pw). Each game must also be launched through Steam in the correct modes before running DeckOps. This creates the Proton prefix and starts shader cache downloads. Skipping this is the most common cause of install failures.

---

## ⚠️ After Installation

**Steam will launch automatically - ignore it and return to Game Mode.** Do not open Steam in Desktop Mode until every modded game has been launched at least once in Game Mode, or Steam Cloud will overwrite your setup.

If asked about cloud saves choose **Keep Local**. If asked about Safe Mode choose **No**.

- **MW1 MP** requires two Steam launches to finish setup, then runs normally on the third.
- **BO2** display settings must be set manually in-game. MP and Zombies configs are written automatically - Singleplayer is encrypted and cannot be set by DeckOps.

---

## Credits

**[PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher)** - Original inspiration for DeckOps.

---

**[Plutonium](https://plutonium.pw)** - MW3, World at War, Black Ops, Black Ops II. 💰 [Donate](https://forum.plutonium.pw/donate)

**[iw4x](https://iw4x.io)** - Modern Warfare 2. [GitHub](https://github.com/iw4x)

**[CoD4x](https://cod4x.ovh)** - Call of Duty 4. [GitHub](https://github.com/callofduty4x)

**[IW3SP-MOD](https://gitea.com/JerryALT/iw3sp_mod)** - CoD4 Campaign mod by JerryALT.

Steam artwork from [SteamGridDB](https://www.steamgriddb.com) - thanks to [Moohoo](https://www.steamgriddb.com/profile/76561198009314736), [jarvis](https://www.steamgriddb.com/profile/76561198103947979), [Ramjez](https://www.steamgriddb.com/profile/76561198122547176), [Over](https://www.steamgriddb.com/profile/76561198049670875), [Uravity-PRO](https://www.steamgriddb.com/profile/76561198167607660), and [Maxine](https://www.steamgriddb.com/profile/76561198130550992).

**[Claude](https://claude.ai)** by Anthropic - assisted in development.

---

> DeckOps is not affiliated with Activision, Infinity Ward, Treyarch, or Valve. All trademarks belong to their respective owners. A legitimate Steam copy of each game is required. DeckOps does not provide or distribute game files.

## License

[MIT License](LICENSE)
