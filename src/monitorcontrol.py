# Keypirinha launcher (keypirinha.com)

import keypirinha as kp
import keypirinha_util as kpu
import keypirinha_net as kpnet
import json
import traceback
import urllib.error
import urllib.parse
import urllib.request
import http.client
import os
from monitorcontrol import get_monitors


class monitorcontrol(kp.Plugin):

    ITEMCAT_RESULT = kp.ItemCategory.USER_BASE + 1
    MONITOR_ITEMS = kp.ItemCategory.USER_BASE + 2

    structure = {}

    """
    One-line description of your plugin.

    This block is a longer and more detailed description of your plugin that may
    span on several lines, albeit not being required by the application.

    You may have several plugins defined in this module. It can be useful to
    logically separate the features of your package. All your plugin classes
    will be instantiated by Keypirinha as long as they are derived directly or
    indirectly from :py:class:`keypirinha.Plugin` (aliased ``kp.Plugin`` here).

    In case you want to have a base class for your plugins, you must prefix its
    name with an underscore (``_``) to indicate Keypirinha it is not meant to be
    instantiated directly.

    In rare cases, you may need an even more powerful way of telling Keypirinha
    what classes to instantiate: the ``__keypirinha_plugins__`` global variable
    may be declared in this module. It can be either an iterable of class
    objects derived from :py:class:`keypirinha.Plugin`; or, even more dynamic,
    it can be a callable that returns an iterable of class objects. Check out
    the ``StressTest`` example from the SDK for an example.

    Up to 100 plugins are supported per module.

    More detailed documentation at: http://keypirinha.com/api/plugin.html
    """
    def __init__(self):
        super().__init__()

    def on_start(self):
        # load ini file
        settings = self.load_settings()
        # get all monitors defined in the ini file
        monitor_sections = [ section.split("/")[0] for section in settings.sections() if section.lower().startswith("monitor/") ]
        
        data = {}

        for section in monitor_sections:
            monitor_id = section[8:]

            data[monitor_id] = {}

            monitors = settings.keys(section)
            for monitor_key in monitors:
                monitor_string = settings.get(monitor_key, section=section)
                if not len(monitor_string):
                    self.warn(
                        'Monitor variable "{}" does not have "string" value (or is empty). Ignored.'.format(
                            monitor_key
                        )
                    )
                    continue

                data[monitor_id][monitor_key] = monitor_string

        self.generate_folder_structure(data) 


       
    def on_catalog(self):
        catalog = []
        # define a catalog item for each monitor
        for monitor in self.monitor_sections:
            catalog.append(
                self.create_item(
                    category=kp.ItemCategory.REFERENCE,
                    label=monitor,
                    short_desc=monitor,
                    target=monitor,
                    args_hint=kp.ItemArgsHint.ACCEPTED,
                    hit_hint=kp.ItemHitHint.KEEPALL,
                )
            )
        self.set_catalog(catalog)

    def on_suggest(self, user_input, items_chain):
        # if nothing has been selected yet
        if not items_chain:
            return
        # if the first item is not a monitor
        if items_chain and (
            items_chain[0].category() != kp.ItemCategory.REFERENCE
            or items_chain[-1].category() != self.MONITOR_ITEMS
        ):
            return
        
        path = [node.label() for node in items_chain]
        structure_ref = self.get_node_from_structure(path)
        nodes = structure_ref.keys()

        suggestions = []

        for node in nodes:
            suggestions.append(
                self.create_item(
                    category=self.MONITOR_ITEMS,
                    label=node,
                    short_desc=node,
                    target=node,
                    args_hint=kp.ItemArgsHint.REQUIRED,
                    hit_hint=kp.ItemHitHint.NOARGS,
                )
            )

        user_input = user_input.strip()

        self.set_suggestions(
            suggestions,
            kp.Match.ANY if not user_input else kp.Match.FUZZY,
            kp.Sort.NONE if not user_input else kp.Sort.SCORE_DESC,
        )

    def on_execute(self, item, action):
        #set values or retrieve infos to clipboard
        return
    
    def generate_folder_structure(self, data):
        self.structure = {}
        for monitor_id in data.keys():
            self.structure[monitor_id] = {}
            for key, value in data[monitor_id].items():
                self.structure[monitor_id][key] = []
                for item in value.split(","):
                    self.structure[monitor_id][key].append(self.create_item(
                    category=self.ITEMCAT_RESULT,
                    label=item.strip(),
                    short_desc=item.strip(),
                    target=key,
                    args_hint=kp.ItemArgsHint.FORBIDDEN,
                    hit_hint=kp.ItemHitHint.IGNORE,
                ))
        return
    
    def get_node_from_structure(self, path):
        structure_ref = self.structure
        for node in path:
            structure_ref = structure_ref[node]
        return structure_ref