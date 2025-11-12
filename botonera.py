# Botonera virtual de sons
# Creada per Carles Ceacero mitjançant Python i Pygame. Amb el suport de la IA.

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import pygame
import keyboard  # Nota: pip install keyboard (pot requerir privilegis)
import numpy as np
import sounddevice as sd
import soundfile as sf
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, Toplevel, Label

# --- Config i logging ---
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("Botonera")

SCRIPT_DIR = Path(__file__).resolve().parent
PERFILS_DIR = SCRIPT_DIR / "perfils"  # <-- NOU: Directori per perfils

# --- Pygame mixer: inicialitzem amb maneig d'errors ---
MIXER_OK = False
try:
    pygame.mixer.init()
    pygame.mixer.set_num_channels(32)
    MIXER_OK = True
    LOG.info("pygame.mixer inicialitzat correctament.")
except Exception as e:
    LOG.exception("No s'ha pogut iniciar pygame.mixer: %s", e)
    MIXER_OK = False

# --- Constants d'enregistrament ---
SAMPLERATE = 44100
CHANNELS = 1
DTYPE = "float32"
FRAMES_PER_BUFFER = 1024

# --- Colors i paleta ---
COLOR_BLAU = "#3c8dbc"
COLOR_VERD = "#00a65a"
COLOR_VERMELL = "#dd4b39"
COLOR_TARONJA = "#f39c12"
COLOR_LILA = "#605ca8"
COLOR_TURQUESA = "#00c0ef"
COLOR_GROC = "#f0db2e"
COLOR_GRIS = "#555"
COLOR_ROSA = "#d81b60"
COLOR_BUIT = "#3c3c3c"
COLOR_REPRODUINT = "#777"

PALETA_COLORS_DICT = {
    "Blau": COLOR_BLAU,
    "Verd": COLOR_VERD,
    "Vermell": COLOR_VERMELL,
    "Taronja": COLOR_TARONJA,
    "Lila": COLOR_LILA,
    "Turquesa": COLOR_TURQUESA,
    "Groc": COLOR_GROC,
    "Gris": COLOR_GRIS,
    "Rosa": COLOR_ROSA,
    "Botó Buit": COLOR_BUIT,
}
REVERSE_PALETA = {v: k for k, v in PALETA_COLORS_DICT.items()}

LLISTA_EMOJIS = [
    "➕", "🎙️", "👏", "😂", "🎺", "❌", "🚪", "🥁", "👽", "📞", "🐶", "🐱", "💥",
    "💧", "🚗", "🔔", "👻", "🤖", "⚡️", "🌊", "🎵", "🎶", "🎤", "🎧", "🔈",
    "🔊", "🔥", "💨", "💬", "🛑", "✅", "⛔", "⚠️", "💯", "💸", "💡", "💣",
    "💀", "❤️", "⭐", "🎉", "🤯", "🤔", "...", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣",
]


# --- Data model per a la configuració d'un botó ---
@dataclass
class ButtonConfig:
    id: int
    emoji: str = "➕"
    nom: str = "Buit"
    arxiu: Optional[str] = None  # camí relatiu respecto SCRIPT_DIR o None
    color: str = COLOR_BUIT
    tecla_assignada: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --- Classe SoundButton simplificada i sense globals ---
class SoundButton:
    def __init__(self, app: "BotoneraApp", parent_frame: tk.Frame, config: ButtonConfig):
        """
        Representa un botó visual que pot reproduir un so i tenir configuració.
        """
        self.app = app
        self.parent_frame = parent_frame
        self.config = config

        self.channel: Optional[pygame.mixer.Channel] = None
        self.is_playing = False

        self.color_text = "black" if self.config.color == COLOR_GROC else "white"

        # Widget container
        self.frame = tk.Frame(self.parent_frame, bg=self.config.color, height=110, width=150)
        self.frame.grid_propagate(False)
        self.frame.pack_propagate(False)

        # Emoji
        self.label_emoji = tk.Label(self.frame, text=self.config.emoji, font=("Segoe UI Emoji", 28, "bold"),
                                    bg=self.config.color, fg=self.color_text)
        self.label_emoji.pack(pady=(20, 5))

        # Nom
        self.label_nom = tk.Label(self.frame, text=self.config.nom, font=("Arial", 11, "bold"),
                                  bg=self.config.color, fg=self.color_text, wraplength=140)
        self.label_nom.pack(pady=(0, 10), fill="x", expand=True, anchor="n")

        # Indicador tecla
        tecla_text = self.config.tecla_assignada.upper() if self.config.tecla_assignada else "--"
        self.label_tecla = tk.Label(self.frame, text=tecla_text, font=("Arial", 9, "bold"),
                                    bg="#222", fg="white", padx=4, pady=2)
        self.label_tecla.place(relx=1.0, rely=0.0, anchor="ne", x=-5, y=5)

        # Menu clic dret
        self.menu = tk.Menu(self.frame, tearoff=0)
        self.menu.add_command(label="Configuració del botó...", command=self.obrir_configuracio)
        self.menu.add_separator()
        self.menu.add_command(label="Tancar")

        # Bindings
        for widget in (self.frame, self.label_emoji, self.label_nom, self.label_tecla):
            widget.bind("<Button-1>", self.on_click_esquerre)
            widget.bind("<Button-3>", self.mostrar_menu_clic_dret)

    def grid(self, row: int, column: int):
        self.frame.grid(row=row, column=column, padx=5, pady=5)

    # ---------- Reproducció ----------
    def on_click_esquerre(self, event=None):
        if not self.config.arxiu:
            self.obrir_configuracio()
        else:
            self.reproduir()

    def reproduir(self):
        if not MIXER_OK:
            LOG.warning("Intent de reproduir sense mixer disponible.")
            return

        volumen = self.app.get_volum_actual()

        # Si ja està sonant, fem stop
        if self.channel and self.channel.get_busy():
            self.channel.stop()
            self.is_playing = False
            self.channel = None
            self._set_default_visuals()
            return

        if not self.config.arxiu:
            LOG.warning("No hi ha arxiu assignat al botó id=%s", self.config.id)
            return

        cami = Path(self.config.arxiu)
        if not cami.is_absolute():
            cami = SCRIPT_DIR / cami

        if not cami.exists():
            LOG.error("Arxiu no trobat: %s", cami)
            messagebox.showerror("Error d'arxiu", f"No s'ha trobat l'arxiu:\n{self.config.arxiu}", parent=self.app.finestra)
            return

        try:
            so = pygame.mixer.Sound(str(cami))
            so.set_volume(1.0)
            chan = pygame.mixer.find_channel()
            if chan is None:
                messagebox.showwarning("Error d'àudio", "No hi ha canals de so lliures!", parent=self.app.finestra)
                return
            chan.set_volume(volumen)
            chan.play(so)
            self.channel = chan
        except Exception as e:
            LOG.exception("Error reproduint %s: %s", cami, e)
            messagebox.showerror("Error de reproducció", f"Error en reproduir l'arxiu:\n{e}", parent=self.app.finestra)

    def update_visuals(self):
        """Sincronitza l'estat visual amb l'estat de reproducció."""
        if not MIXER_OK:
            return
        is_busy = self.channel and self.channel.get_busy()
        if is_busy and not self.is_playing:
            self._set_playing_visuals()
            self.is_playing = True
        elif not is_busy and self.is_playing:
            self._set_default_visuals()
            self.is_playing = False
            self.channel = None

    def _set_playing_visuals(self):
        self.frame.config(bg=COLOR_REPRODUINT)
        self.label_emoji.config(bg=COLOR_REPRODUINT)
        self.label_nom.config(bg=COLOR_REPRODUINT)
        self.label_tecla.config(bg=COLOR_REPRODUINT)

    def _set_default_visuals(self):
        self.frame.config(bg=self.config.color)
        self.label_emoji.config(bg=self.config.color, fg="black" if self.config.color == COLOR_GROC else "white")
        self.label_nom.config(bg=self.config.color)
        self.label_tecla.config(bg="#222")

    # ---------- Configuració (popup) ----------
    def mostrar_menu_clic_dret(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def assignar_arxiu(self):
        nou = filedialog.askopenfilename(parent=self.top_config, title="Selecciona un arxiu de so",
                                         filetypes=[("Arxius de so", "*.wav *.mp3"), ("Tots els arxius", "*.*")])
        if not nou:
            return
        cami = Path(nou)
        try:
            rel = cami.relative_to(SCRIPT_DIR)
            cami_rel = str(rel)
        except Exception:
            cami_rel = str(cami)
        self.config.arxiu = cami_rel
        if self.config.nom == "Buit":
            self.config.nom = cami.stem
            if hasattr(self, "entry_nom"):
                self.entry_nom.delete(0, tk.END)
                self.entry_nom.insert(0, self.config.nom)
        self.label_nom.config(text=self.config.nom)

    def iniciar_assignacio_tecla(self):
        self._toggle_config_widgets("disabled")
        self.btn_canviar_tecla.config(text="... Prem una tecla ...")
        try:
            self._tecla_handle = keyboard.on_press(self._capturar_tecla, suppress=True)
        except Exception as e:
            LOG.exception("Error iniciant escolta de tecles: %s", e)
            messagebox.showerror("Error de permisos", "No s'ha pogut iniciar l'escolta de tecles.\nExecuta com a administrador si cal.",
                                 parent=self.top_config)
            self._toggle_config_widgets("normal")

    def _capturar_tecla(self, event):
        nova = getattr(event, "name", None) or str(event)
        # Desenganxem l'escolta
        try:
            if hasattr(self, "_tecla_handle"):
                keyboard.unhook(self._tecla_handle)
                del self._tecla_handle
        except Exception:
            pass

        # Si tecla en ús per un altre config -> error
        conflict = self.app.hotkey_registry.get(nova)
        if conflict and conflict["config"].id != self.config.id:
            altre_nom = conflict["config"].nom
            messagebox.showerror("Tecla en ús", f"La tecla '{nova.upper()}' ja està assignada a '{altre_nom}'.", parent=self.top_config)
            self._toggle_config_widgets("normal")
            return

        # Eliminar hotkey antiga si existeix
        antiga = self.config.tecla_assignada
        if antiga and antiga in self.app.hotkey_registry:
            handle_ant = self.app.hotkey_registry[antiga]["handle"]
            try:
                keyboard.remove_hotkey(handle_ant)
            except Exception:
                LOG.warning("No s'ha pogut eliminar hotkey antiga: %s", antiga)
            self.app.hotkey_registry.pop(antiga, None)

        self.config.tecla_assignada = nova
        # Registrar nova hotkey i guardar el handle
        try:
            handle = keyboard.add_hotkey(nova, lambda: self.reproduir())
            self.app.hotkey_registry[nova] = {"config": self.config, "handle": handle}
        except Exception as e:
            LOG.exception("No s'ha pogut assignar hotkey %s: %s", nova, e)
            messagebox.showerror("Error de permisos", "No s'ha pogut assignar la tecla. Executa com a administrador si cal.", parent=self.top_config)
            self._toggle_config_widgets("normal")
            return

        # Actualitzar etiqueta
        if hasattr(self, "label_tecla_config"):
            tecla_text = self.config.tecla_assignada.upper() if self.config.tecla_assignada else "--"
            self.label_tecla_config.config(text=f"Tecla assignada: {tecla_text}")

        self._toggle_config_widgets("normal")
        # Actualitzar la petita etiqueta del botó principal
        self.label_tecla.config(text=self.config.tecla_assignada.upper() if self.config.tecla_assignada else "--")

    def _toggle_config_widgets(self, estat: str):
        state_combo = "readonly" if estat == "normal" else "disabled"
        widgets = ["combo_emoji", "entry_nom", "combo_color", "btn_canviar_arxiu", "btn_desar", "btn_canviar_tecla"]
        # Controls s'han creat a obrir_configuracio
        for name in widgets:
            widget = getattr(self, name, None)
            if widget:
                try:
                    if name.startswith("combo_"):
                        widget.config(state=state_combo)
                    else:
                        widget.config(state=estat)
                except Exception:
                    pass

    def obrir_configuracio(self):
        self.top_config = Toplevel(self.app.finestra)
        self.top_config.title("Configuració del botó")
        self.top_config.config(bg="#333")
        self.top_config.attributes("-topmost", True)
        self.top_config.grab_set()

        # Emoji
        f_emoji = tk.Frame(self.top_config, bg="#333")
        f_emoji.pack(padx=15, pady=10, fill="x")
        Label(f_emoji, text="Icona (Emoji):", font=("Arial", 10), fg="white", bg="#333").pack(anchor="w")
        self.combo_emoji = ttk.Combobox(f_emoji, values=LLISTA_EMOJIS, state="readonly", font=("Segoe UI Emoji", 16), width=8)
        self.combo_emoji.pack(anchor="w")
        try:
            idx = LLISTA_EMOJIS.index(self.config.emoji)
            self.combo_emoji.current(idx)
        except ValueError:
            self.combo_emoji.current(0)

        # Nom
        f_nom = tk.Frame(self.top_config, bg="#333")
        f_nom.pack(padx=15, pady=(0, 10), fill="x")
        Label(f_nom, text="Nom (text curt):", font=("Arial", 10), fg="white", bg="#333").pack(anchor="w")
        self.entry_nom = tk.Entry(f_nom, font=("Arial", 14), width=30)
        self.entry_nom.pack(fill="x", expand=True)
        self.entry_nom.insert(0, self.config.nom)

        # Color
        f_color = tk.Frame(self.top_config, bg="#333")
        f_color.pack(padx=15, pady=(0, 10), fill="x")
        Label(f_color, text="Color del botó:", font=("Arial", 10), fg="white", bg="#333").pack(anchor="w")
        self.combo_color = ttk.Combobox(f_color, values=list(PALETA_COLORS_DICT.keys()), state="readonly", font=("Arial", 14), width=28)
        self.combo_color.pack(fill="x", expand=True)
        nom_color_actual = REVERSE_PALETA.get(self.config.color, "Gris")
        self.combo_color.set(nom_color_actual)

        # Accions
        f_accions = tk.Frame(self.top_config, bg="#333")
        f_accions.pack(padx=15, pady=10, fill="x")

        self.btn_canviar_arxiu = tk.Button(f_accions, text="🔊 Canviar arxiu de so...", command=self.assignar_arxiu)
        self.btn_canviar_arxiu.pack(fill="x", pady=5)

        tecla_text_config = self.config.tecla_assignada.upper() if self.config.tecla_assignada else "--"
        self.label_tecla_config = Label(f_accions, text=f"Tecla assignada: {tecla_text_config}", font=("Arial", 10), fg="white", bg="#333")
        self.label_tecla_config.pack(anchor="w", pady=5)

        self.btn_canviar_tecla = tk.Button(f_accions, text="🎹 Canviar tecla...", command=self.iniciar_assignacio_tecla)
        self.btn_canviar_tecla.pack(fill="x", pady=5)

        # Desar
        self.btn_desar = tk.Button(self.top_config, text="Desar canvis", font=("Arial", 12, "bold"), command=self.desar_configuracio)
        self.btn_desar.pack(pady=15, padx=15, fill="x")

    def desar_configuracio(self):
        nou_emoji = self.combo_emoji.get()
        nou_nom = self.entry_nom.get().strip()
        nou_color_nom = self.combo_color.get()

        if nou_emoji:
            self.config.emoji = nou_emoji
            self.label_emoji.config(text=self.config.emoji)
        if nou_nom:
            self.config.nom = nou_nom
            self.label_nom.config(text=self.config.nom)
        if nou_color_nom:
            nou_color_hex = PALETA_COLORS_DICT.get(nou_color_nom)
            if nou_color_hex:
                self.config.color = nou_color_hex
                self.color_text = "black" if nou_color_hex == COLOR_GROC else "white"
                self.frame.config(bg=nou_color_hex)
                self.label_emoji.config(bg=nou_color_hex, fg=self.color_text)
                self.label_nom.config(bg=nou_color_hex, fg=self.color_text)

        # actualitzar la petita etiqueta de la tecla
        tecla_text = self.config.tecla_assignada.upper() if self.config.tecla_assignada else "--"
        self.label_tecla.config(text=tecla_text)

        try:
            self.top_config.destroy()
        except Exception:
            pass


# --- Classe principal de l'aplicació ---
class BotoneraApp:
    def __init__(self, root: tk.Tk):
        self.finestra = root
        self.finestra.title("Botonera virtual de sons - Perfil Nou")
        self.finestra.config(bg="#1e1e1e")
        self.finestra.resizable(False, False)

        self.volum_actual = 0.8
        self.botons_widgets: List[SoundButton] = []
        self.hotkey_registry: Dict[str, Dict[str, Any]] = {}  # tecla -> {"config": ButtonConfig, "handle": handle}

        self.totes_les_configuracions: List[ButtonConfig] = []
        self.preparar_configuracions()

        # NOU: Assegurem que el directori de perfils existeix
        try:
            PERFILS_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            LOG.warning("No s'ha pogut crear el directori de perfils: %s", e)

        self.arxiu_perfil_actual: Optional[str] = None

        # Grab dels estats d'enregistrament
        self.is_recording = False
        self.recording_frames: List[np.ndarray] = []
        self.recording_thread: Optional[threading.Thread] = None
        self.last_recording_path_relatiu: Optional[str] = None

        self.btn_record: Optional[tk.Button] = None
        self.blink_after_id: Optional[str] = None
        self.blink_on = False

        self.configurar_estil_ttk()
        self.configurar_finestra()
        self.crear_controls_superiors()
        self.crear_frame_graella()

        self.on_format_graella_canvia()

        self.finestra.protocol("WM_DELETE_WINDOW", self.en_tancar)
        if MIXER_OK:
            self._update_playback_loop()

    def preparar_configuracions(self):
        self.totes_les_configuracions.clear()
        for i in range(24):
            cfg = ButtonConfig(id=i)
            self.totes_les_configuracions.append(cfg)

    def configurar_finestra(self):
        # icona (opcional)
        try:
            ico = SCRIPT_DIR / "icona.ico"
            if ico.exists():
                self.finestra.iconbitmap(str(ico))
        except Exception:
            LOG.debug("No s'ha pogut carregar icona.ico", exc_info=True)

    def configurar_estil_ttk(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
            style.configure('TCombobox',
                            fieldbackground='#333',
                            background='#333',
                            foreground='white',
                            arrowcolor='white',
                            bordercolor="#1e1e1e")
            style.map('TCombobox',
                      fieldbackground=[('readonly', '#333')],
                      background=[('readonly', '#333')],
                      foreground=[('readonly', 'white')],
                      selectbackground=[('readonly', '#333')],
                      selectforeground=[('readonly', 'white')])
            self.finestra.option_add('*TCombobox*Listbox.background', '#333')
            self.finestra.option_add('*TCombobox*Listbox.foreground', 'white')
            self.finestra.option_add('*TCombobox*Listbox.selectBackground', COLOR_BLAU)
            self.finestra.option_add('*TCombobox*Listbox.selectForeground', 'white')
        except Exception:
            LOG.debug("Problema aplicant estil ttk", exc_info=True)

    def crear_controls_superiors(self):
        frame = tk.Frame(self.finestra, bg="#1e1e1e")
        frame.pack(fill="x", padx=10, pady=(5, 10))

        self.btn_record = tk.Button(frame, text="Enregistra", command=self.toggle_enregistrament,
                                    bg=COLOR_VERMELL, fg="white", relief="flat")
        self.btn_record.pack(side="left", padx=5, ipady=2)

        tk.Button(frame, text="Nou Perfil", command=self.nou_perfil, bg=COLOR_TARONJA, fg="white", relief="flat").pack(side="left", padx=5, ipady=2)
        tk.Button(frame, text="Carregar Perfil", command=self.carregar_perfil, bg=COLOR_BLAU, fg="white", relief="flat").pack(side="left", padx=5, ipady=2)
        tk.Button(frame, text="Desar Perfil", command=self.desar_perfil_actual, bg=COLOR_VERD, fg="white", relief="flat").pack(side="left", padx=5, ipady=2)
        tk.Button(frame, text="Desar Com...", command=self.desar_perfil_com, bg=COLOR_GRIS, fg="white", relief="flat").pack(side="left", padx=5, ipady=2)

        tk.Button(frame, text="Quant a...", command=self.mostrar_about, bg=COLOR_LILA, fg="white", relief="flat").pack(side="left", padx=(5, 10), ipady=2)

        # volum
        tk.Label(frame, text="Volum:", font=("Arial", 11), fg="white", bg="#1e1e1e").pack(side="left", padx=(10, 5))
        slider = tk.Scale(frame, from_=0, to=100, orient="horizontal", command=self.canviar_volum, bg="#1e1e1e",
                          fg="white", troughcolor="#555", showvalue=0, length=150, relief="flat", borderwidth=0, highlightthickness=0)
        slider.set(int(self.volum_actual * 100))
        slider.pack(side="left", pady=3)
        self.etiqueta_valor_volum = tk.Label(frame, text=f"{int(self.volum_actual * 100)}%", font=("Arial", 11, "bold"),
                                             fg="white", bg="#1e1e1e", width=4)
        self.etiqueta_valor_volum.pack(side="left", padx=5)

        # format graella
        tk.Label(frame, text="Format:", font=("Arial", 11), fg="white", bg="#1e1e1e").pack(side="left", padx=(15, 5))
        self.formats_graella = {
            "6x1 (6 botons)": (6, 1),
            "6x2 (12 botons)": (6, 2),
            "6x3 (18 botons)": (6, 3),
            "6x4 (24 botons)": (6, 4),
        }
        self.combo_format_graella = ttk.Combobox(frame, values=list(self.formats_graella.keys()), state="readonly",
                                                 font=("Arial", 10), width=15)
        self.combo_format_graella.set("6x4 (24 botons)")
        self.combo_format_graella.pack(side="left", padx=5, pady=8)
        self.combo_format_graella.bind("<<ComboboxSelected>>", self.on_format_graella_canvia)

    def crear_frame_graella(self):
        self.frame_graella = tk.Frame(self.finestra, bg="#1e1e1e")
        self.frame_graella.pack(fill="both", expand=True, padx=20, pady=10)

    def on_format_graella_canvia(self, event=None):
        key = self.combo_format_graella.get()
        tup = self.formats_graella.get(key, (6, 4))
        self.regenerar_graella(tup)

    def regenerar_graella(self, format_tuple):
        # Netegem widgets previs
        for w in self.frame_graella.winfo_children():
            w.destroy()
        self.botons_widgets.clear()

        # Esborrem hotkeys registrades prèviament de forma segura
        for tecla, info in list(self.hotkey_registry.items()):
            try:
                handle = info.get("handle")
                if handle:
                    keyboard.remove_hotkey(handle)
            except Exception:
                LOG.debug("No s'ha pogut eliminar hotkey %s", tecla)
        self.hotkey_registry.clear()

        cols, rows = format_tuple
        total = cols * rows

        for i in range(total):
            if i >= len(self.totes_les_configuracions):
                break
            cfg = self.totes_les_configuracions[i]
            fila = i // cols
            col = i % cols
            btn = SoundButton(self, self.frame_graella, cfg)
            btn.grid(row=fila, column=col)
            self.botons_widgets.append(btn)
            # registrar hotkey si existeix
            if cfg.tecla_assignada:
                try:
                    handle = keyboard.add_hotkey(cfg.tecla_assignada, lambda cfg=cfg: self._play_by_config(cfg))
                    self.hotkey_registry[cfg.tecla_assignada] = {"config": cfg, "handle": handle}
                except Exception:
                    LOG.warning("No s'ha pogut registrar hotkey inicial %s", cfg.tecla_assignada)

        self.finestra.update_idletasks()
        self.centrar_finestra()

    def _play_by_config(self, cfg: ButtonConfig):
        # trobem el widget associat i cridem reproduir
        for b in self.botons_widgets:
            if b.config.id == cfg.id:
                b.reproduir()
                return

    def nou_perfil(self):
        confirmar = messagebox.askyesno("Crear nou perfil", "Segur que vols esborrar la configuració actual? Aquesta acció no es pot desfer.", parent=self.finestra)
        if not confirmar:
            return
        self.arxiu_perfil_actual = None
        self.finestra.title("Botonera virtual de sons - Perfil Nou")
        self.preparar_configuracions()
        self.combo_format_graella.set("6x4 (24 botons)")
        self.regenerar_graella((6, 4))

    def carregar_perfil(self):
        arxiu = filedialog.askopenfilename(title="Carregar perfil de botonera",
                                         filetypes=[("Perfils JSON", "*.json"), ("Tots els arxius", "*.*")],
                                         defaultextension=".json",
                                         initialdir=str(PERFILS_DIR))  # <-- MODIFICAT
        if not arxiu:
            return
        try:
            with open(arxiu, "r", encoding="utf-8") as f:
                dades = json.load(f)
            loaded = [ButtonConfig(**d) for d in dades.get("configuracions", [])]
            # Ens assegurem que tinguem 24 configs
            while len(loaded) < 24:
                loaded.append(ButtonConfig(id=len(loaded)))
            self.totes_les_configuracions = loaded[:24]
            fmt = dades.get("format_graella", "6x4 (24 botons)")
            if fmt not in self.formats_graella:
                fmt = "6x4 (24 botons)"
            self.combo_format_graella.set(fmt)
            self.regenerar_graella(self.formats_graella[fmt])
            self.arxiu_perfil_actual = arxiu
            self.finestra.title(f"Botonera virtual de sons - {Path(arxiu).name}")
        except Exception as e:
            LOG.exception("Error carregant perfil %s", arxiu)
            messagebox.showerror("Error de càrrega", f"Error en carregar el perfil:\n{e}", parent=self.finestra)

    def desar_perfil_actual(self):
        if not self.arxiu_perfil_actual:
            self.desar_perfil_com()
        else:
            self.desar_perfil(self.arxiu_perfil_actual)

    def desar_perfil_com(self):
        arxiu = filedialog.asksaveasfilename(title="Desar perfil com...",
                                           filetypes=[("Perfils JSON", "*.json"), ("Tots els arxius", "*.*")],
                                           defaultextension=".json",
                                           initialdir=str(PERFILS_DIR))  # <-- MODIFICAT
        if arxiu:
            self.desar_perfil(arxiu)

    def desar_perfil(self, path: str):
        try:
            fmt = self.combo_format_graella.get()
            dades = {
                "format_graella": fmt,
                "configuracions": [c.to_dict() for c in self.totes_les_configuracions[:24]]
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(dades, f, indent=4, ensure_ascii=False)
            self.arxiu_perfil_actual = path
            self.finestra.title(f"Botonera virtual de sons - {Path(path).name}")
        except Exception as e:
            LOG.exception("Error desant perfil")
            messagebox.showerror("Error en desar", f"No s'ha pogut desar el perfil:\n{e}", parent=self.finestra)

    def centrar_finestra(self):
        self.finestra.update_idletasks()
        w = self.finestra.winfo_reqwidth()
        h = self.finestra.winfo_reqheight()
        sw = self.finestra.winfo_screenwidth()
        sh = self.finestra.winfo_screenheight()
        x = max((sw // 2) - (w // 2), 0)
        y = max((sh // 2) - (h // 2), 0)
        self.finestra.geometry(f"{w}x{h}+{x}+{y}")

    def parar_tots_els_sons(self):
        if not MIXER_OK:
            return
        pygame.mixer.stop()

    def canviar_volum(self, valor):
        if not MIXER_OK:
            return
        try:
            v = float(valor) / 100.0
            self.volum_actual = v
            self.etiqueta_valor_volum.config(text=f"{int(float(valor))}%")
            # Ajustem volums dels canals ocupats
            for b in self.botons_widgets:
                if b.channel and b.channel.get_busy():
                    try:
                        b.channel.set_volume(self.volum_actual)
                    except Exception:
                        pass
        except Exception:
            LOG.debug("Valor de volum incorrecte: %s", valor)

    def get_volum_actual(self) -> float:
        return self.volum_actual

    def _update_playback_loop(self):
        for b in self.botons_widgets:
            b.update_visuals()
        try:
            self.finestra.after(100, self._update_playback_loop)
        except tk.TclError:
            pass

    # ---------------- Enregistrament ----------------
    def toggle_enregistrament(self):
        if self.is_recording:
            self.aturar_enregistrament()
        else:
            self.iniciar_enregistrament()

    def iniciar_enregistrament(self):
        if not MIXER_OK:
            messagebox.showerror("Error d'àudio", "No s'ha pogut iniciar el dispositiu d'àudio (mixer).", parent=self.finestra)
            return
        self.is_recording = True
        self.recording_frames.clear()
        self.parar_tots_els_sons()
        self.recording_thread = threading.Thread(target=self._tasca_enregistrament, daemon=True)
        self.recording_thread.start()
        self._iniciar_blink()

    def _tasca_enregistrament(self):
        try:
            with sd.InputStream(samplerate=SAMPLERATE, channels=CHANNELS, dtype=DTYPE, blocksize=FRAMES_PER_BUFFER) as stream:
                LOG.info("Enregistrament iniciat...")
                while self.is_recording:
                    frames, overflowed = stream.read(FRAMES_PER_BUFFER)
                    if overflowed:
                        LOG.warning("Overflow en enregistrament.")
                    self.recording_frames.append(frames)
        except Exception as e:
            LOG.exception("Error durant l'enregistrament: %s", e)
            self.is_recording = False
            self.finestra.after(0, lambda: messagebox.showerror("Error d'enregistrament", f"No s'ha pogut accedir al micròfon:\n{e}", parent=self.finestra))
        LOG.info("Enregistrament aturat.")

    def aturar_enregistrament(self):
        if not self.recording_thread:
            return
        self.is_recording = False
        self._aturar_blink()
        if self.btn_record:
            self.btn_record.config(text="PROCESSANT...", state="disabled")
        self.finestra.after(100, self._finalitzar_enregistrament)

    def _finalitzar_enregistrament(self):
        if self.recording_thread:
            self.recording_thread.join()
            self.recording_thread = None
        if self.btn_record:
            self.btn_record.config(text="Enregistra", state="normal", bg=COLOR_VERMELL, activebackground=COLOR_VERMELL)

        if not self.recording_frames:
            LOG.info("No s'ha enregistrat res.")
            return

        try:
            recording = np.concatenate(self.recording_frames, axis=0)
        except Exception:
            LOG.exception("Error concatenant enregistraments")
            return

        enregistraments_dir = SCRIPT_DIR / "enregistraments"
        enregistraments_dir.mkdir(parents=True, exist_ok=True)
        filename = f"enregistrament_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        rel_path = Path("enregistraments") / filename
        self.last_recording_path_relatiu = str(rel_path)
        cami_absolut = SCRIPT_DIR / rel_path

        try:
            sf.write(str(cami_absolut), recording, SAMPLERATE)
            LOG.info("Arxiu desat a: %s", cami_absolut)
        except Exception as e:
            LOG.exception("Error desant arxiu: %s", e)
            messagebox.showerror("Error en desar", f"No s'ha pogut desar l'arxiu .wav:\n{e}", parent=self.finestra)
            return

        # Preguntem si volem assignar al primer botó buit
        self.demanar_desar_enregistrament()

    def demanar_desar_enregistrament(self):
        conservar = messagebox.askyesno("Enregistrament finalitzat", "Enregistrament completat!\n\nVols assignar aquest enregistrament al primer botó buit?", parent=self.finestra)
        if conservar:
            self.afegir_enregistrament_a_boto()
        else:
            try:
                toremove = SCRIPT_DIR / self.last_recording_path_relatiu
                if toremove.exists():
                    toremove.unlink()
                    LOG.info("Arxiu descartat esborrat: %s", toremove)
            except Exception:
                LOG.debug("No s'ha pogut esborrar l'arxiu descartat.")

    def afegir_enregistrament_a_boto(self):
        index_buit = -1
        for i, cfg in enumerate(self.totes_les_configuracions):
            if not cfg.arxiu and cfg.nom == "Buit":
                index_buit = i
                break
        if index_buit == -1:
            messagebox.showwarning("Graella plena", "No s'ha trobat cap botó buit. L'enregistrament s'ha desat a la carpeta 'enregistraments'.", parent=self.finestra)
            return
        cfg = self.totes_les_configuracions[index_buit]
        cfg.arxiu = self.last_recording_path_relatiu
        cfg.nom = Path(self.last_recording_path_relatiu).stem
        cfg.emoji = "🎙️"
        cfg.color = COLOR_LILA
        # regen to show changes
        self.on_format_graella_canvia()
        LOG.info("Enregistrament assignat al botó %d", index_buit + 1)

    def _iniciar_blink(self):
        self.blink_on = True
        self._fer_blink()

    def _aturar_blink(self):
        self.blink_on = False
        if self.blink_after_id:
            try:
                self.finestra.after_cancel(self.blink_after_id)
            except Exception:
                pass
            self.blink_after_id = None
        if self.btn_record:
            self.btn_record.config(text="Enregistra", bg=COLOR_VERMELL, activebackground=COLOR_VERMELL)

    def _fer_blink(self):
        if not self.blink_on or not self.btn_record:
            return
        try:
            current = self.btn_record.cget("bg")
            self.btn_record.config(bg=COLOR_GRIS if current == COLOR_VERMELL else COLOR_VERMELL, activebackground=COLOR_GRIS if current == COLOR_VERMELL else COLOR_VERMELL)
            self.blink_after_id = self.finestra.after(500, self._fer_blink)
        except tk.TclError:
            self.blink_on = False

    # ---------- About ----------
    def mostrar_about(self):
        text_about = """BOTONERA VIRTUAL DE SONS v1.0

Copyright (c) 2025 Carles Ceacero

Es concedeix permís, de forma gratuïta, a qualsevol persona que obtingui una còpia d'aquest programari i dels fitxers de documentació associats (el "Programari"), per tractar-hi sense restriccions, incloent-hi els drets d'ús, còpia, modificació, fusió, publicació, distribució, sublicència o venda de còpies del Programari, i per permetre a les persones a qui es lliuri el Programari a fer-ho, amb subjecte a les condicions següents:

La nota de copyright anterior i aquest avís de permís s'han d'incloure en totes les còpies o parts substancials del Programari.

EL PROGRAMARI ES PROPORCIONA "TAL QUAL", SENSE CAP GARANTIA DE CAP MENA, EXPRESSA O IMPLÍCITA, INCLOSA PERÒ NO LIMITADA A LES GARANTIES DE COMERCIALITZACIÓ, ADEQUACIÓ PER A UN PROPÒSIT PARTICULAR I NO VIOLACIÓ DE DRETS. EN CAP CAS ELS AUTORS O TITULARS DEL COPYRIGHT SERAN RESPONSABLES PER RECLAMACIONS, DANYS O ALTRES RESPONSABILITATS, SIGUI EN UNA ACCIÓ CONTRACTUAL, AGREUJANT O ALTRA, PROCEDENTS DE, O RELACIONADES AMB EL PROGRAMARI O L'ÚS O ALTRES OPERACIONS EN EL PROGRAMARI."""
        messagebox.showinfo("Quant a Botonera", text_about, parent=self.finestra)

    # ---------- Tancar ----------
    def en_tancar(self):
        LOG.info("Tancant l'aplicació...")
        self.is_recording = False
        try:
            if MIXER_OK:
                pygame.mixer.quit()
        except Exception:
            LOG.debug("Error tancant mixer", exc_info=True)

        # eliminar hotkeys
        for tecla, info in list(self.hotkey_registry.items()):
            try:
                handle = info.get("handle")
                if handle:
                    keyboard.remove_hotkey(handle)
            except Exception:
                pass
        try:
            self.finestra.destroy()
        except Exception:
            pass


# --- Main ---
def main():
    # comprova si som admin per a mostrar missatge; no fem obligatori però informem
    is_admin = False
    try:
        import platform
        if platform.system() == "Windows":
            import ctypes
            is_admin = (ctypes.windll.shell32.IsUserAnAdmin() != 0)
        else:
            is_admin = (os.getuid() == 0)
    except Exception:
        LOG.debug("No s'ha pogut comprovar permisos d'admin.")

    if not is_admin:
        LOG.info("Alerta: l'aplicació no s'està executant com a Administrador. Les tecles globals podrien no funcionar.")

    root = tk.Tk()
    app = BotoneraApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()