from functools import lru_cache
from pathlib import Path
from typing import List, Union

import oead
from bcml import mergers, util


def get_stock_quests() -> oead.byml.Array:
    title_sarc = oead.Sarc(
        util.get_game_file('Pack/TitleBG.pack').read_bytes()
    )
    return oead.byml.from_binary(
        util.decompress(title_sarc.get_file('Quest/QuestProduct.sbquestpack').data)
    )


class QuestMerger(mergers.Merger):
    NAME: str = 'quests'

    def __init__(self):
        super().__init__('quests', 'Merges changes to Quest.product.byml',
                         'quests.yml', options={})

    def generate_diff(self, mod_dir: Path, modded_files: List[Union[Path, str]]):
        if f'{util.get_content_path()}/Pack/TitleBG.pack//Quest/QuestProduct.sbquestpack' not in modded_files:
            return {}
        stock_quests = get_stock_quests()
        stock_names = [q['Name'] for q in stock_quests]

        title_sarc = oead.Sarc(
            (mod_dir / util.get_content_path() / 'Pack' / 'TitleBG.pack').read_bytes()
        )
        mod_quests = oead.byml.from_binary(
            util.decompress(title_sarc.get_file('Quest/QuestProduct.sbquestpack').data)
        )
        mod_names = [q['Name'] for q in mod_quests]
        diffs = oead.byml.Hash({
            'add': oead.byml.Array(),
            'mod': oead.byml.Hash(),
            'del': oead.byml.Array({
                q for q in stock_names if q not in mod_names
            })
        })

        for quest in mod_quests:
            quest_name = quest['Name']
            if quest_name not in stock_names:
                diffs['add'].append(quest)
            elif quest != stock_quests[stock_names.index(quest_name)]:
                diffs['mod'][quest_name] = quest

        return diffs

    def log_diff(self, mod_dir: Path, diff_material):
        if isinstance(diff_material, list):
            diff_material = self.generate_diff(mod_dir, diff_material)
        if diff_material:
            (mod_dir / 'logs' / self._log_name).write_text(
                oead.byml.to_text(diff_material),
                encoding='utf-8'
            )

    def get_mod_diff(self, mod: util.BcmlMod):
        diffs = []
        if self.is_mod_logged(mod):
            diffs.append(oead.byml.from_text(
                (mod.path / 'logs' / self._log_name).read_text(encoding='utf-8')
            ))
        for opt in {d for d in (mod.path / 'options').glob('*') if d.is_dir()}:
            if (opt / 'logs' / self._log_name).exists():
                diffs.append(
                    oead.byml.from_text(
                        (opt / 'logs' / self._log_name).read_text('utf-8')
                    )
                )
        return diffs

    def get_all_diffs(self):
        diffs = []
        for mod in util.get_installed_mods():
            diffs.extend(self.get_mod_diff(mod))
        return diffs

    def consolidate_diffs(self, diffs: list):
        all_diffs = oead.byml.Hash({
            'add': oead.byml.Array(),
            'mod': oead.byml.Hash(),
            'del': oead.byml.Array()
        })
        added_quests = set()
        for diff in reversed(diffs):
            for add in diff['add']:
                if add['Name'] not in added_quests:
                    all_diffs['add'].append(add)
                    added_quests.add(add['Name'])
            for name, mod in diff['mod'].items():
                all_diffs['mod'][name] = mod
            for delete in diff['del']:
                if delete not in all_diffs['del']:
                    all_diffs['del'].append(delete)
        return all_diffs

    @util.timed
    def perform_merge(self):
        merged_quests = util.get_master_modpack_dir() / 'logs' / 'quests.byml'
        print('Loading quest mods...')
        diffs = self.consolidate_diffs(self.get_all_diffs())
        if not diffs:
            print('No quest merging necessary')
            if merged_quests.exists():
                merged_quests.unlink()
                util.inject_file_into_titlebg(
                    'Quest/QuestProduct.sbquestpack',
                    util.get_nested_file_bytes(
                        (f'{str(util.get_game_file("Pack/TitleBG.pack"))}'
                         '//Quest/QuestProduct.sbquestpack'),
                        unyaz=False
                    )
                )
            return
        print('Loading stock quests...')
        quests = get_stock_quests()
        stock_names = [q['Name'] for q in quests]

        print('Merging quest mods...')
        for name, mod in diffs['mod'].items():
            try:
                quests[stock_names.index(name)] = mod
            except ValueError:
                diffs['add'].append(mod)
        for delete in diffs['del']:
            try:
                quests.remove(quests[stock_names.index(delete)])
            except ValueError:
                pass
        added_names = set()
        for add in diffs['add']:
            if add['Name'] not in added_names:
                quests.append(add)
                added_names.add(add['Name'])

        print('Writing new quest pack...')
        data = oead.byml.to_binary(quests, big_endian=util.get_settings('wiiu'))
        merged_quests.parent.mkdir(parents=True, exist_ok=True)
        merged_quests.write_bytes(data)
        util.inject_file_into_titlebg(
            'Quest/QuestProduct.sbquestpack',
            util.compress(data),
            create_titlebg=True
        )

    def get_mod_edit_info(self, mod: util.BcmlMod) -> set:
        diff = self.consolidate_diffs(self.get_mod_diff(mod))
        return (
            {a['Name'] for a in diff['add']} | set(diff['mod'].keys()) | set(diff['del'])
        )

    def get_checkbox_options(self):
        return []
