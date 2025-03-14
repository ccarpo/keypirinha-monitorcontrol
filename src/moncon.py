# Keypirinha launcher (keypirinha.com)

import keypirinha as kp
import keypirinha_util as kpu
from .lib.monitorcontrol import get_monitors
from .lib.monitorcontrol import InputSource, PowerMode
import time


class moncon(kp.Plugin):
    """
    Monitor Control Plugin für Keypirinha.
    Ermöglicht die Steuerung von Monitoren über DDC/CI.
    """

    ITEMCAT_RESULT = kp.ItemCategory.USER_BASE + 1
    MONITOR_ITEMS = kp.ItemCategory.USER_BASE + 2

    def __init__(self):
        super().__init__()
        self.monitors = None
        self.structure = {}
        self.monitor_sections = []
        self.current_states = {}  # Speichert aktuelle Monitoreinstellungen
        self.input_mapping = {}  # Wird in on_start geladen

    def on_start(self):
        self.info("Moncon Plugin startet")
        
        # Input-Mapping aus INI laden
        settings = self.load_settings()
        self.input_mapping = {}
        for key in settings.keys(section="input_mapping"):
            try:
                code = int(key)
                name = settings.get_stripped(key, section="input_mapping")
                self.input_mapping[code] = name
            except ValueError:
                self.warn(f"Ungültiger Input-Code in INI: {key}")
        
        try:
            self.dbg("Versuche Monitore zu initialisieren...")
            self.monitors = get_monitors()
            self.dbg(f"Gefundene Monitore: {len(self.monitors)}")
            
            # Detaillierte Monitor-Informationen
            for idx, monitor in enumerate(self.monitors):
                self.dbg(f"Monitor {idx}:")
                with monitor:
                    try:
                        caps = monitor.get_vcp_capabilities()
                        self.dbg(f"  - Capabilities: {caps}")
                    except Exception as e:
                        self.err(f"  - Fehler beim Lesen der Capabilities: {str(e)}")
            
            self._update_monitor_states()
            
        except Exception as e:
            import traceback
            self.err(f"Kritischer Fehler: {str(e)}")
            self.err(f"Traceback:\n{traceback.format_exc()}")
            return

        # Einstellungen laden
        settings = self.load_settings()
        self.monitor_sections = [
            section.split("/")[1] 
            for section in settings.sections() 
            if section.lower().startswith("monitor/")
        ]
        
        self.generate_folder_structure(settings)

    def on_catalog(self):
        catalog = []
        
        for monitor_id in self.current_states:
            # Konfiguration für diesen Monitor laden
            monitor_section = f"monitor/{monitor_id}"
            settings = self.load_settings()
            display_name = settings.get("display_name", section=monitor_section, fallback=monitor_id)
            
            # Aktuellen Status für die Beschreibung verwenden
            current_state = self.current_states.get(monitor_id, {})
            current_input = self._get_input_name(current_state.get('input', None))
            current_brightness = current_state.get('brightness')
            
            # Beschreibung mit aktuellen Werten
            desc_parts = []
            if current_input:
                desc_parts.append(f"Input: {current_input}")
            if current_brightness is not None:
                desc_parts.append(f"Helligkeit: {current_brightness}%")
            
            desc = ", ".join(desc_parts) if desc_parts else "Status nicht verfügbar"
            
            catalog.append(self.create_item(
                category=kp.ItemCategory.REFERENCE,
                label=f"Monitor: {display_name}",
                short_desc=desc,
                target=monitor_id,
                args_hint=kp.ItemArgsHint.ACCEPTED,
                hit_hint=kp.ItemHitHint.NOARGS
            ))

        self.set_catalog(catalog)

    def on_suggest(self, user_input, items_chain):
        if not items_chain:
            return
        
        if items_chain[0].category() == kp.ItemCategory.REFERENCE:
            monitor_id = items_chain[0].target()
            monitor_state = self.current_states.get(monitor_id, {})
            
            suggestions = []
            
            # 1. Input-Auswahl
            current_input = self._get_input_name(monitor_state.get('input', None))
            capabilities = monitor_state.get('capabilities', {})
            available_inputs = capabilities.get('inputs', [])
            
            # Input-Liste filtern
            settings = self.load_settings()
            show_all = settings.get_bool("show_all_inputs", section="main", fallback=True)
            configured_inputs = settings.get_stripped(
                "inputs",
                section=f"monitor/{monitor_id}",
                fallback=""
            )
            
            filtered_inputs = []
            if configured_inputs and not show_all:
                configured_inputs = [i.strip().upper() for i in configured_inputs.split(",")]
                for input_source in available_inputs:
                    input_name = self._get_input_name(input_source)
                    if input_name in configured_inputs:
                        filtered_inputs.append(input_source)
            else:
                filtered_inputs = available_inputs
            
            # Zusätzliche Inputs aus dem Mapping hinzufügen
            input_mapping_values = set()
            for code, name in self.input_mapping.items():
                if not show_all and configured_inputs:
                    if name not in configured_inputs:
                        continue
                input_mapping_values.add(code)
                if code not in [getattr(x, 'value', x) for x in filtered_inputs]:
                    filtered_inputs.append(code)
            
            for input_source in filtered_inputs:
                input_name = self._get_input_name(input_source)
                if input_name and not input_name.startswith("0x"):
                    suggestions.append(
                        self.create_item(
                            category=self.ITEMCAT_RESULT,
                            label=f"Input: {input_name}",
                            short_desc=f"Wechsle zu {input_name}" + (" (Aktuell)" if input_name == current_input else ""),
                            target=f"{monitor_id}/input/{input_source.value if isinstance(input_source, InputSource) else input_source}",
                            args_hint=kp.ItemArgsHint.FORBIDDEN,
                            hit_hint=kp.ItemHitHint.NOARGS
                        )
                    )
            
            # 2. Helligkeit
            current_brightness = monitor_state.get('brightness')
            if current_brightness is not None:
                for value in [0, 25, 50, 75, 100]:
                    suggestions.append(
                        self.create_item(
                            category=self.ITEMCAT_RESULT,
                            label=f"Helligkeit: {value}%",
                            short_desc=f"Helligkeit auf {value}% setzen" + (" (Aktuell)" if value == current_brightness else ""),
                            target=f"{monitor_id}/helligkeit/{value}",
                            args_hint=kp.ItemArgsHint.FORBIDDEN,
                            hit_hint=kp.ItemHitHint.NOARGS
                        )
                    )
            
            # 3. Kontrast
            current_contrast = monitor_state.get('contrast')
            if current_contrast is not None:
                for value in [0, 25, 50, 75, 100]:
                    suggestions.append(
                        self.create_item(
                            category=self.ITEMCAT_RESULT,
                            label=f"Kontrast: {value}%",
                            short_desc=f"Kontrast auf {value}% setzen" + (" (Aktuell)" if value == current_contrast else ""),
                            target=f"{monitor_id}/kontrast/{value}",
                            args_hint=kp.ItemArgsHint.FORBIDDEN,
                            hit_hint=kp.ItemHitHint.NOARGS
                        )
                    )
            
            # 4. Lautstärke
            current_volume = monitor_state.get('volume')
            if current_volume is not None:
                for value in [0, 25, 50, 75, 100]:
                    suggestions.append(
                        self.create_item(
                            category=self.ITEMCAT_RESULT,
                            label=f"Lautstärke: {value}%",
                            short_desc=f"Lautstärke auf {value}% setzen" + (" (Aktuell)" if value == current_volume else ""),
                            target=f"{monitor_id}/volume/{value}",
                            args_hint=kp.ItemArgsHint.FORBIDDEN,
                            hit_hint=kp.ItemHitHint.NOARGS
                        )
                    )
            
            # 5. Preset
            settings = self.load_settings()
            presets = settings.keys(section="presets")
            for preset in presets:
                suggestions.append(
                    self.create_item(
                        category=self.ITEMCAT_RESULT,
                        label=f"Preset: {preset.capitalize()}",
                        short_desc=f"Aktiviere {preset}-Modus",
                        target=f"{monitor_id}/preset/{preset}",
                        args_hint=kp.ItemArgsHint.FORBIDDEN,
                        hit_hint=kp.ItemHitHint.NOARGS
                    )
                )
            
            # Nur setzen wenn wir tatsächlich Vorschläge haben
            if suggestions:
                self.set_suggestions(suggestions)
        
        # Untermenüs für Input
        elif items_chain[-1].target().endswith('/input'):
            monitor_id = items_chain[-1].target().split('/')[0]
            monitor_state = self.current_states.get(monitor_id, {})
            
            # Input-Liste filtern
            capabilities = monitor_state.get('capabilities', {})
            available_inputs = capabilities.get('inputs', [])
            
            settings = self.load_settings()
            show_all = settings.get_bool("show_all_inputs", section="main", fallback=True)
            configured_inputs = settings.get_stripped(
                "inputs",
                section=f"monitor/{monitor_id}",
                fallback=""
            )
            
            filtered_inputs = []
            if configured_inputs and not show_all:
                configured_inputs = [i.strip().upper() for i in configured_inputs.split(",")]
                for input_source in available_inputs:
                    input_name = self._get_input_name(input_source)
                    if input_name in configured_inputs:
                        filtered_inputs.append(input_source)
            else:
                filtered_inputs = available_inputs
            
            suggestions = []
            for input_source in filtered_inputs:
                input_name = self._get_input_name(input_source)
                if input_name and not input_name.startswith("0x"):
                    suggestions.append(
                        self.create_item(
                            category=self.ITEMCAT_RESULT,
                            label=input_name,
                            short_desc=f"Wechsle zu {input_name}",
                            target=f"{monitor_id}/input/{input_source.value if isinstance(input_source, InputSource) else input_source}",
                            args_hint=kp.ItemArgsHint.FORBIDDEN,
                            hit_hint=kp.ItemHitHint.NOARGS
                        )
                    )
            
            self.set_suggestions(suggestions)
        
        # Untermenüs für Helligkeit/Kontrast/Lautstärke
        elif items_chain[-1].target().endswith(('/helligkeit', '/kontrast', '/volume')):
            monitor_id = items_chain[-1].target().split('/')[0]
            control_type = items_chain[-1].target().split('/')[-1]
            
            # Aktuelle Werte aus dem Monitor-Status holen
            monitor_state = self.current_states.get(monitor_id, {})
            current_value = None
            if control_type == 'helligkeit':
                current_value = monitor_state.get('brightness')
            elif control_type == 'kontrast':
                current_value = monitor_state.get('contrast')
            elif control_type == 'volume':
                current_value = monitor_state.get('volume')
            
            # Standard-Schritte
            values = [0, 25, 50, 75, 100]
            
            # Wenn es einen aktuellen Wert gibt, diesen auch hinzufügen
            if current_value is not None and current_value not in values:
                values.append(current_value)
                values.sort()
            
            suggestions = [
                self.create_item(
                    category=self.ITEMCAT_RESULT,
                    label=f"{value}%",
                    short_desc=f"{control_type.capitalize()} auf {value}% setzen",
                    target=f"{items_chain[-1].target()}/{value}",
                    args_hint=kp.ItemArgsHint.FORBIDDEN,
                    hit_hint=kp.ItemHitHint.NOARGS
                ) for value in values
            ]
            self.set_suggestions(suggestions)
        
        # Untermenüs
        elif items_chain[-1].target().endswith('/preset'):
            settings = self.load_settings()
            presets = settings.keys(section="presets")
            suggestions = [
                self.create_item(
                    category=self.ITEMCAT_RESULT,
                    label=preset.capitalize(),
                    short_desc=f"Aktiviere {preset}-Modus",
                    target=f"{items_chain[-1].target()}/{preset}",
                    args_hint=kp.ItemArgsHint.FORBIDDEN,
                    hit_hint=kp.ItemHitHint.NOARGS
                ) for preset in presets
            ]
            self.set_suggestions(suggestions)

    def on_execute(self, item, action):
        if item.category() == self.ITEMCAT_RESULT:
            try:
                path = item.target().split('/')
                monitor_id = path[0]
                command = path[1]
                value = path[2] if len(path) > 2 else None
                
                # Monitor finden
                monitor = None
                for idx, m in enumerate(self.monitors):
                    with m:
                        caps = m.get_vcp_capabilities()
                        if f"{caps.get('model', f'Monitor{idx}')}_{idx}" == monitor_id:
                            monitor = m
                            break
                
                if not monitor:
                    self.warn(f"Monitor {monitor_id} nicht gefunden!")
                    return
                
                with monitor:
                    if command == "input":
                        try:
                            value = int(value)
                            self.info(f"Setze Eingang auf {value} ({item.label()})")
                            monitor.set_input_source(value)
                            time.sleep(1)  # Kurze Pause für den Monitor
                            
                            try:
                                actual_input = monitor.get_input_source()
                                if isinstance(actual_input, InputSource):
                                    actual_value = actual_input.value
                                else:
                                    actual_value = actual_input
                                    
                                if actual_value == value:
                                    self.info(f"Eingang erfolgreich auf {item.label()} gesetzt")
                                else:
                                    self.warn(f"Eingang möglicherweise nicht korrekt gesetzt. Ist: {self._get_input_name(actual_input)}")
                            except Exception as verify_error:
                                self.dbg(f"Konnte Input-Status nicht verifizieren: {str(verify_error)}")
                                self.info(f"Eingang auf {item.label()} gesetzt (ohne Verifikation)")
                                
                        except Exception as e:
                            self.err(f"Fehler beim Setzen des Eingangs: {str(e)}")
                            self.warn("Überprüfen Sie, ob der Monitor diesen Eingang unterstützt")
                    
                    elif command == "helligkeit":
                        try:
                            value = int(value)
                            monitor.set_luminance(value)
                            self.info(f"Helligkeit auf {value}% gesetzt")
                        except Exception as e:
                            self.err(f"Fehler beim Setzen der Helligkeit: {str(e)}")
                    
                    elif command == "kontrast":
                        try:
                            value = int(value)
                            monitor.set_contrast(value)
                            self.info(f"Kontrast auf {value}% gesetzt")
                        except Exception as e:
                            self.err(f"Fehler beim Setzen des Kontrasts: {str(e)}")
                    
                    elif command == "volume":
                        try:
                            value = int(value)
                            monitor.set_audio_volume(value)
                            self.info(f"Lautstärke auf {value}% gesetzt")
                        except Exception as e:
                            self.err(f"Fehler beim Setzen der Lautstärke: {str(e)}")
                    
                    elif command == "preset":
                        try:
                            settings = self.load_settings()
                            preset_config = settings.get_stripped(value, section="presets")
                            if preset_config:
                                for setting in preset_config.split(','):
                                    key, val = setting.strip().split(':')
                                    if key == 'brightness':
                                        monitor.set_luminance(int(val))
                                    elif key == 'contrast':
                                        monitor.set_contrast(int(val))
                                    elif key == 'color':
                                        # TODO: Implementiere Farbprofil-Wechsel
                                        pass
                                self.info(f"Preset {value} aktiviert")
                        except Exception as e:
                            self.err(f"Fehler beim Aktivieren des Presets: {str(e)}")
                
                self._update_monitor_states()
                
            except Exception as e:
                self.err(f"Ausführungsfehler: {str(e)}")
                self.warn("Bitte überprüfen Sie die Monitor-Einstellungen")

    def _update_monitor_states(self):
        """Aktualisiert den Status aller Monitore"""
        self.dbg("Starte Monitor-Status Update")
        
        if not self.monitors:
            self.warn("Keine Monitore verfügbar für Status-Update")
            return
            
        for idx, monitor in enumerate(self.monitors):
            try:
                self.dbg(f"Lese Status von Monitor {monitor}")
                
                with monitor:
                    # Capabilities für Monitor-ID holen
                    try:
                        caps = monitor.get_vcp_capabilities()
                        monitor_id = f"{caps.get('model', f'Monitor{idx}')}_{idx}"
                    except Exception as e:
                        self.dbg(f"Fehler beim Lesen der Capabilities: {str(e)}")
                        monitor_id = f"Monitor{idx}"
                        caps = {}
                    
                    # Einzelne Operationen mit Try/Except
                    try:
                        input_source = monitor.get_input_source()
                        self.dbg(f"Input Source: {input_source}")
                    except Exception as e:
                        self.dbg(f"Fehler beim Lesen der Eingangsquelle: {str(e)}")
                        input_source = None

                    try:
                        luminance = monitor.get_luminance()
                        self.dbg(f"Luminance: {luminance}")
                    except Exception as e:
                        self.dbg(f"Fehler beim Lesen der Helligkeit: {str(e)}")
                        luminance = None

                    try:
                        contrast = monitor.get_contrast()
                        self.dbg(f"Contrast: {contrast}")
                    except Exception as e:
                        self.dbg(f"Fehler beim Lesen des Kontrasts: {str(e)}")
                        contrast = None

                    try:
                        volume = monitor.get_audio_volume()
                        self.dbg(f"Volume: {volume}")
                    except Exception as e:
                        self.dbg(f"Fehler beim Lesen der Lautstärke: {str(e)}")
                        volume = None

                    # Verfügbare Inputs aus Capabilities extrahieren
                    if 'inputs' not in caps:
                        try:
                            available_inputs = []
                            for code in range(1, 32):  # Typische Range für Input-Codes
                                try:
                                    if monitor.get_vcp_feature(0x60, code):  # 0x60 ist der VCP-Code für Input Source
                                        available_inputs.append(code)
                                except:
                                    pass
                            caps['inputs'] = available_inputs
                        except Exception as e:
                            self.dbg(f"Fehler beim Ermitteln der verfügbaren Inputs: {str(e)}")
                            caps['inputs'] = []

                monitor_info = {
                    'input': input_source,
                    'brightness': luminance,
                    'contrast': contrast,
                    'volume': volume,
                    'capabilities': caps
                }
                
                # Aktuellen Status mit vorherigem Status zusammenführen
                if monitor_id in self.current_states:
                    old_state = self.current_states[monitor_id]
                    # Nur gültige neue Werte übernehmen
                    monitor_info = {
                        key: value if value is not None else old_state.get(key)
                        for key, value in monitor_info.items()
                    }
                    # Capabilities zusammenführen
                    if 'capabilities' in old_state:
                        old_caps = old_state['capabilities']
                        if 'inputs' in old_caps and not caps.get('inputs'):
                            caps['inputs'] = old_caps['inputs']
                
                self.current_states[monitor_id] = monitor_info
                self.dbg(f"Monitor {monitor_id} Status erfolgreich aktualisiert")
                
            except Exception as e:
                self.err(f"Fehler beim Lesen des Monitor-Status")
                self.err(f"Error: {str(e)}")
                import traceback
                self.err(f"Traceback:\n{traceback.format_exc()}")

    def _get_input_name(self, input_value):
        """Konvertiert DDC/CI Werte zurück in lesbare Namen"""
        if input_value is None:
            return "Unbekannt"
        
        # Wenn input_value bereits ein InputSource-Enum ist
        if isinstance(input_value, InputSource):
            return input_value.name
            
        # Für numerische Werte aus INI-Mapping
        return self.input_mapping.get(input_value, f"0x{int(input_value):02x}")

    def _get_input_value(self, input_name):
        """Konvertiert Namen zurück in DDC/CI Werte"""
        # Reverse-Mapping erstellen
        reverse_mapping = {v: k for k, v in self.input_mapping.items()}
        return reverse_mapping.get(input_name.upper())

    def generate_folder_structure(self, settings):
        self.structure = {}
        
        for monitor_id in self.monitor_sections:
            section = f"monitor/{monitor_id}"
            self.structure[monitor_id] = {}
            
            # Input-Optionen laden
            inputs = settings.get_stripped("inputs", section=section)
            if inputs:
                self.structure[monitor_id]["input"] = [
                    input.strip() for input in inputs.split(",")
                ]

            # Weitere Optionen hier laden...

    def get_node_from_structure(self, path):
        structure_ref = self.structure
        for node in path:
            structure_ref = structure_ref[node]
        return structure_ref