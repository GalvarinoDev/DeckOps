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
- Each game installed through Steam and launched at least once (both SP and MP modes)
- Plutonium games require a free account at [plutonium.pw](https://plutonium.pw)

> DeckOps will show which games haven't been launched yet and prevent you from selecting them until ready.

---

## ⚠️ After Installation

**Launch Steam in Desktop Mode before switching to Game Mode.** This lets Steam reload the config changes DeckOps made. Then switch to Game Mode and play normally.

---

## 🎮 Supported Games

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

> **Steam Deck LCD:** Plutonium servers require OLED. For offline Campaign and Zombies on LCD, see [PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher).

---

## 🔧 Troubleshooting

**Shortcuts not using GE-Proton?**
Go to **Settings → Repair Shortcuts** to re-apply GE-Proton and controller configs.

**Controller profiles not working?**
Go to **Settings → Re-apply Templates** to reinstall controller profiles.

**Game asks for Safe Mode or override config?**
Choose **No** — DeckOps has already configured optimal settings.

**Cloud save out of sync?**
Choose **Keep Local** to preserve DeckOps settings.

---

## Credits

DeckOps is an installer. The projects below are what actually make it work.

**[PlutoniumAltLauncher](https://github.com/framilano/PlutoniumAltLauncher)** - Original inspiration for DeckOps.

**[Plutonium](https://plutonium.pw)** - MW3, World at War, Black Ops, Black Ops II. 💰 [Donate](https://forum.plutonium.pw/donate)

**[iw4x](https://iw4x.io)** - Modern Warfare 2. [GitHub](https://github.com/iw4x)

**[CoD4x](https://cod4x.ovh)** - Call of Duty 4. [GitHub](https://github.com/callofduty4x)

**[IW3SP-MOD](https://gitea.com/JerryALT/iw3sp_mod)** - CoD4 Campaign mod by JerryALT.

Steam artwork from [SteamGridDB](https://www.steamgriddb.com) — thanks to Moohoo, jarvis, Ramjez, Over, Uravity-PRO, and Maxine.

**[Claude](https://claude.ai)** by Anthropic — assisted in development.

---

## License

[MIT License](LICENSE)

DeckOps is not affiliated with Activision, Infinity Ward, Treyarch, or Valve. All trademarks belong to their respective owners.
