# Firmware ESP32 — Nouveautés

Historique des versions du firmware ESP32 d'Edilkamin Control. Le firmware s'installe depuis la [page d'installation](https://akoonet-homeassistant.github.io/edilkamin_control/webflash/) ou, depuis la 2026.11.2, à distance depuis Home Assistant (**Paramètres → Mises à jour → Firmware de l'ESP32**).

Ces versions ne sont pas des releases GitHub : les releases du dépôt sont celles de l'intégration (HACS).

*English version below.*

## 2026.11.6
- **Télécommande sur la page web de l'ESP32** : marche/arrêt, consigne par pas de 0,5 °C, puissance (Auto, P1 à P5), ventilations 1 et 2, Stand-by et Silence (Relax).
- L'arrêt se confirme par un second appui (le bouton devient « Confirmer l'arrêt » pendant 4 s). La consigne part 1,2 s après le dernier appui sur − ou +.
- Les ordres passent par l'ESP32, comme ceux de Home Assistant, et fonctionnent aussi quand Home Assistant est absent. Un changement de consigne est vu par l'intégration comme une dérogation, gardée jusqu'au prochain changement de plage.
- Sécurité : les ordres exigent un en-tête propre à la page (un autre site ne peut pas les envoyer) ; seuls les ordres de la télécommande sont acceptés.

## 2026.11.5
- La page web affiche le **planning de secours** reçu de Home Assistant : horaires, jours, consigne, Marche ou Stand-by, puissance, ventilations et silence de chaque plage. La plage appliquée est mise en évidence quand le planning de secours est actif.
- Tous les textes affichés sur la page web sont échappés (protection contre l'injection de code).

## 2026.11.4
- Température ambiante transmise au dixième de degré à Home Assistant : la précision du thermostat passe de 0,5 °C à 0,1 °C. La consigne reste réglable par pas de 0,5 °C.

## 2026.11.3
- Le Bluetooth du poêle est libéré plus vite : température lue en premier, lectures rapprochées, déconnexion dès que toutes les valeurs sont relues (au lieu de rester 30 s). La télécommande et l'application Edilkamin trouvent le poêle libre plus souvent.
- Nouveaux capteurs « Occupation du Bluetooth » (% sur 15 min) et « Durée de connexion Bluetooth », aussi affichés sur la page web.

## 2026.11.2
- Page web d'état à l'adresse de l'ESP32, protégée par mot de passe (identifiant `admin`, mot de passe réglé dans Home Assistant).
- Adresse IP publiée en MQTT (entité « ESP32 adresse IP », lien « Visiter » sur l'appareil).
- Mise à jour à distance depuis Home Assistant ou depuis la page web, avec contrôle MD5 et retour à la version précédente en cas d'échec.
- Puissance manuelle (Man. P1 à P5) : le mode automatique du poêle est coupé avant l'envoi, la puissance est enfin appliquée.
- Lecture de l'horloge du poêle (valeurs brutes).

## 2026.11.1
- Planning de secours v2 : jusqu'à 10 plages, jours de la semaine et silence (Relax), envoyé par l'intégration. Le format v1 (5 plages) reste accepté.
- Version du firmware affichée dans Home Assistant.

---

# ESP32 firmware — What's new

Version history of the Edilkamin Control ESP32 firmware. Install it from the [install page](https://akoonet-homeassistant.github.io/edilkamin_control/webflash/) or, since 2026.11.2, remotely from Home Assistant (**Settings → Updates → ESP32 firmware**).

These versions are not GitHub releases: the repository releases are the integration's (HACS).

## 2026.11.6
- **Remote control on the ESP32 web page**: on/off, setpoint in 0.5 °C steps, power (Auto, P1 to P5), fans 1 and 2, Stand-by and Silent (Relax).
- Turning off is confirmed by a second tap (the button becomes “Confirmer l'arrêt” for 4 s). The setpoint is sent 1.2 s after the last − or + tap.
- Commands go through the ESP32, like Home Assistant's, and also work when Home Assistant is down. A setpoint change is seen by the integration as an override, kept until the next slot change.
- Security: commands require a page-specific header (another site cannot send them); only remote-control commands are accepted.

## 2026.11.5
- The web page shows the **fallback schedule** received from Home Assistant: times, days, setpoint, On or Stand-by, power, fans and silent mode of each slot. The applied slot is highlighted when the fallback schedule is active.
- All text shown on the web page is escaped (protection against code injection).

## 2026.11.4
- Room temperature passed to Home Assistant to a tenth of a degree: thermostat precision goes from 0.5 °C to 0.1 °C. The setpoint is still set in 0.5 °C steps.

## 2026.11.3
- The stove Bluetooth is released sooner: temperature read first, reads closer together, disconnection as soon as all values are read (instead of staying 30 s). The remote and the Edilkamin app find the stove free more often.
- New “Bluetooth occupancy” (% over 15 min) and “Bluetooth connection duration” sensors, also shown on the web page.

## 2026.11.2
- Status web page at the ESP32 address, password protected (user `admin`, password set in Home Assistant).
- IP address published over MQTT (“ESP32 IP address” entity, “Visit” link on the device).
- Remote update from Home Assistant or the web page, with MD5 check and rollback on failure.
- Manual power (Man. P1 to P5): the stove's automatic mode is turned off first, so the power is now applied.
- Stove clock read (raw values).

## 2026.11.1
- Fallback schedule v2: up to 10 slots, days of the week and silent mode, sent by the integration. v1 (5 slots) still accepted.
- Firmware version shown in Home Assistant.
