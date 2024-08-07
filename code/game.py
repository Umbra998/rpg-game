import sys

import pygame.display

from settings import *
from config_manager import config_manager
from save_manager import save_manager
from random import randint, uniform

from support import *
from game_data import game_data
from timer import Timer

from sprites import Sprite, AnimatedSprite, MonsterPatchSprite, BorderSprite, CollidableSprite, TransitionSprite
from entities import Player, Characters
from groups import AllSprites
from monster import Monster
from monster_inventory import MonsterInventory
from battle import Battle
from evolution import Evolution
from options import Options

from dialogue import DialogueTree

from debug import debug


class Game:
    # general setup
    def __init__(self, open_main_menu, save_data=None):
        self.display_surface = pygame.display.get_surface()
        self.clock = pygame.time.Clock()

        # player monsters
        self.player_monsters = {
            0: Monster('Plumette', 5),
            1: Monster('Sparchu', 5),
            2: Monster('Finsta', 5),
        }

        # groups
        self.collision_sprites = pygame.sprite.Group()
        self.all_sprites = AllSprites(self.collision_sprites)
        self.character_sprites = pygame.sprite.Group()
        self.transition_sprites = pygame.sprite.Group()
        self.encounter_sprites = pygame.sprite.Group()

        # transition / tint
        self.transition_target = None
        self.tint_surf = pygame.Surface((config_manager.settings['video']['window_width'],
                                         config_manager.settings['video']['window_height']))
        self.tint_mode = 'untint'
        self.tint_progress = 0
        self.tint_direction = -1
        self.tint_speed = 600

        # setup
        self.current_world = 'world'
        self.import_assets()
        self.setup(self.tmx_maps[self.current_world], 'start')
        self.audio['music_overworld'].play(loops=-1, fade_ms=1000)

        # overlays
        self.dialogue_tree = None
        self.monster_index = MonsterInventory(self.player_monsters, self.fonts, self.monster_frames)
        self.monster_index_open = False
        self.battle = None

        # encounter
        self.encounter_timer = Timer(250)
        self.spawn_chance = 90
        self.evolution = None
        self.evolution_queue = []

        # options
        self.functions = {
            'open_main_menu': open_main_menu,
            'close_game': self.close,
            'adjust_surfaces': self.adjust_surfaces,
            'adjust_fonts': self.adjust_fonts,
            'adjust_audio': self.adjust_volume,
            'save': self.save_game,
            'load': self.load_game
        }
        self.options = Options(self.bg_frames['forest'], self.functions)
        self.options_open = False
        self.closing = False
        self.running = True

        if save_data:
            self.load_game(save_data, True)

        self.start_up_delay = Timer(250, autostart=True)

    def import_assets(self):
        self.tmx_maps = import_tmx_maps('..', 'data', 'maps')

        self.overworld_frames = {
            'water': import_folder('..', 'graphics', 'tilesets', 'water'),
            'coast': import_coastline(24, 12, '..', 'graphics', 'tilesets', 'coast'),
            'characters': import_all_characters('..', 'graphics', 'characters')
        }

        self.monster_frames = {
            'icons': import_folder_dict('..', 'graphics', 'icons'),
            'monsters': import_monster(4, 2, '..', 'graphics', 'monsters'),
            'attacks': import_attacks('..', 'graphics', 'attacks'),
            'ui': import_folder_dict('..', 'graphics', 'ui')
        }
        self.monster_frames['outlines'] = outline_creator(self.monster_frames['monsters'], 4)

        self.bg_frames = import_folder_dict('..', 'graphics', 'backgrounds')

        self.star_animation_frames = import_folder('..', 'graphics', 'other', 'star animation')

        screen_width, _ = self.display_surface.get_size()
        font_size_ratio = 0.015
        font_size = int(screen_width * font_size_ratio)
        self.fonts = {
            'dialogue': pygame.font.Font(join('..', 'graphics', 'fonts', 'PixeloidSans.ttf'), font_size),
            'regular': pygame.font.Font(join('..', 'graphics', 'fonts', 'PixeloidSans.ttf'), font_size),
            'small': pygame.font.Font(join('..', 'graphics', 'fonts', 'PixeloidSans.ttf'), int(font_size * 0.6)),
            'bold': pygame.font.Font(join('..', 'graphics', 'fonts', 'dogicapixelbold.otf'), font_size)
        }

        self.audio = audio_importer('..', 'audio')
        self.adjust_volume('music')
        self.adjust_volume('sfx')

    def setup(self, tmx_map, player_start_pos):
        # clear the map
        for group in (self.collision_sprites, self.all_sprites, self.character_sprites, self.transition_sprites):
            group.empty()

        # terrain
        for layer in ['Terrain', 'Terrain Top']:
            for x, y, surf in tmx_map.get_layer_by_name(layer).tiles():
                Sprite((x * TILE_SIZE, y * TILE_SIZE), surf, self.all_sprites, WORLD_LAYERS['bg'])

        # water
        for obj in tmx_map.get_layer_by_name('Water'):
            for x in range(int(obj.x), int(obj.x + obj.width), TILE_SIZE):
                for y in range(int(obj.y), int(obj.y + obj.height), TILE_SIZE):
                    AnimatedSprite((x, y), self.overworld_frames['water'], self.all_sprites, WORLD_LAYERS['water'])

        # coast
        for obj in tmx_map.get_layer_by_name('Coast'):
            terrain = obj.properties['terrain']
            side = obj.properties['side']
            AnimatedSprite((obj.x, obj.y), self.overworld_frames['coast'][terrain][side], self.all_sprites,
                           WORLD_LAYERS['bg'])

        # grass patches
        for obj in tmx_map.get_layer_by_name('Monsters'):
            MonsterPatchSprite((obj.x, obj.y), obj.image, (self.all_sprites, self.encounter_sprites),
                               obj.properties['biome'], obj.properties['min_level'], obj.properties['max_level'],
                               obj.properties['monsters'])

        # collision objects
        for obj in tmx_map.get_layer_by_name('Collisions'):
            BorderSprite((obj.x, obj.y), pygame.Surface((obj.width, obj.height)), self.collision_sprites)

        # objects
        for obj in tmx_map.get_layer_by_name('Objects'):
            if obj.name == 'top':
                Sprite((obj.x, obj.y), obj.image, self.all_sprites, WORLD_LAYERS['top'])
            else:
                CollidableSprite((obj.x, obj.y), obj.image, (self.all_sprites, self.collision_sprites))

        # transition objects
        for obj in tmx_map.get_layer_by_name('Transition'):
            TransitionSprite((obj.x, obj.y), (obj.width, obj.height), (obj.properties['target'], obj.properties['pos']),
                             self.transition_sprites)

        # entities
        player_created = False
        for obj in tmx_map.get_layer_by_name('Entities'):
            if obj.name == 'Player':
                if obj.properties['pos'] == player_start_pos:
                    self.player = Player(
                        pos=(obj.x, obj.y),
                        frames=self.overworld_frames['characters']['player'],
                        groups=self.all_sprites,
                        facing_direction=obj.properties['direction'],
                        collision_sprites=self.collision_sprites
                    )
                    player_created = True
        for obj in tmx_map.get_layer_by_name('Entities'):
            if obj.name != 'Player':
                Characters(
                    pos=(obj.x, obj.y),
                    frames=self.overworld_frames['characters'][obj.properties['graphic']],
                    groups=(self.all_sprites, self.collision_sprites, self.character_sprites),
                    facing_direction=obj.properties['direction'],
                    character_data=game_data.character_data[obj.properties['character_id']],
                    player=self.player,
                    create_dialogue=self.create_dialogue,
                    collision_sprites=self.collision_sprites,
                    radius=obj.properties['radius'],
                    char_id=obj.properties['character_id'],
                    sounds=self.audio
                )

        if not player_created:
            # Create the player at the start position if not already created
            self.player = Player(
                pos=player_start_pos,
                frames=self.overworld_frames['characters']['player'],
                groups=self.all_sprites,
                facing_direction='down',  # Default facing direction
                collision_sprites=self.collision_sprites
            )

    # dialogue system
    def input(self):
        if not self.dialogue_tree and not self.battle:
            keys = pygame.key.get_just_pressed()
            if (keys[config_manager.settings['controls']['confirm'][0]] and not self.player.blocked)\
                    or (keys[config_manager.settings['controls']['confirm'][1]] and not self.player.blocked):
                for character in self.character_sprites:
                    if check_connection(TILE_SIZE * 2, self.player, character, 30):
                        self.player.block()
                        character.change_facing_direction(self.player.rect.center)
                        self.create_dialogue(character)
                        character.can_rotate = False
            if keys[pygame.K_TAB] or keys[pygame.K_i]:
                self.player.blocked = not self.player.blocked
                self.monster_index_open = not self.monster_index_open
            if keys[pygame.K_ESCAPE]:
                if self.monster_index_open:
                    self.player.unblock()
                    self.monster_index_open = False
                else:
                    self.options.run()
            if keys[pygame.K_F5]:
                if not self.options_open and not self.monster_index_open:
                    self.save_game(f'sfslotqs{VERSION}.json')
            if keys[pygame.K_F9]:
                if not self.options_open and not self.monster_index_open:
                    self.load_game(f'sfslotqs{VERSION}.json')

    def create_dialogue(self, character):
        if not self.dialogue_tree:
            self.dialogue_tree = DialogueTree(character, self.player, self.all_sprites, self.fonts['dialogue'],
                                              self.end_dialogue)
            character.block()

    def end_dialogue(self, character):
        self.dialogue_tree = None
        if character.char_id == 'Nurse':
            for monster in self.player_monsters.values():
                monster.health = monster.get_stat('max_health')
                monster.energy = monster.get_stat('max_energy')
            self.player.unblock()
        elif not character.character_data['defeated']:
            self.audio['music_overworld'].fadeout(1000)
            self.audio['music_battle'].play(loops=-1, fade_ms=4000)

            self.transition_target = Battle(
                player_monsters=self.player_monsters,
                opponent_monsters=character.monsters,
                monster_frames=self.monster_frames,
                bg_surf=self.bg_frames[character.character_data['biome']],
                fonts=self.fonts,
                end_battle=self.end_battle,
                character=character,
                check_evolution=self.check_evolution,
                sounds=self.audio
            )

            self.tint_mode = 'tint'
        elif not self.evolution:
            self.player.unblock()

    # battle encounters
    def check_for_monster(self):
        if [sprite for sprite in self.encounter_sprites if sprite.rect.colliderect(self.player.hitbox)]\
                and not self.battle and self.player.direction:
            if not self.encounter_timer.active:
                self.encounter_timer.activate()
                x = randint(0, 100)
                if x >= self.spawn_chance:
                    self.monster_encounter()
        else:
            self.encounter_timer.deactivate()

    def monster_encounter(self):
        sprites = [sprite for sprite in self.encounter_sprites if sprite.rect.colliderect(self.player.hitbox)]
        if sprites and self.player.direction:
            # block player
            self.player.block()

            # create encounters
            wild_monsters = {}
            amount = randint(1, 3)
            for i in range(amount):
                lvl = randint(sprites[0].min_lvl, sprites[0].max_lvl)
                monster_index = randint(0, len(sprites[0].monsters) - 1)
                new_monster = Monster(sprites[0].monsters[monster_index], lvl)
                wild_monsters[i] = new_monster

            self.audio['music_overworld'].fadeout(1000)
            self.audio['music_battle'].play(loops=-1, fade_ms=4000)

            # battle
            self.transition_target = Battle(
                player_monsters=self.player_monsters,
                opponent_monsters=wild_monsters,
                monster_frames=self.monster_frames,
                bg_surf=self.bg_frames[sprites[0].biome],
                fonts=self.fonts,
                end_battle=self.end_battle,
                character=None,
                check_evolution=self.check_evolution,
                sounds=self.audio
            )
            self.tint_mode = 'tint'

    def end_battle(self, character):
        self.audio['music_battle'].fadeout(1000)
        self.audio['music_overworld'].play(loops=-1, fade_ms=1000)

        self.transition_target = 'level'
        self.tint_mode = 'tint'
        if character:
            character.character_data['defeated'] = True
            # game_data.character_data[character]
            self.create_dialogue(character)
        elif not self.evolution:
            self.player.unblock()

    # transition system
    def transition_check(self):
        sprites = [sprite for sprite in self.transition_sprites if sprite.rect.colliderect(self.player.hitbox)]
        if sprites:
            self.player.block()
            self.transition_target = sprites[0].target
            self.tint_mode = 'tint'

    def tint_screen(self, dt):
        if self.tint_mode == 'untint':
            self.tint_progress -= self.tint_speed * dt

        if self.tint_mode == 'tint':
            self.tint_progress += self.tint_speed * dt
            if self.tint_progress >= 255:
                if type(self.transition_target) is Battle:
                    self.battle = self.transition_target
                elif self.transition_target == 'level':
                    self.battle = None
                else:
                    self.setup(self.tmx_maps[self.transition_target[0]], self.transition_target[1])
                    self.current_world = self.transition_target[0]
                self.tint_mode = 'untint'
                self.transition_target = None

        self.tint_progress = max(0, min(self.tint_progress, 255))
        self.tint_surf.set_alpha(self.tint_progress)
        self.display_surface.blit(self.tint_surf, (0, 0))

    # evolutions
    def check_evolution(self):
        for index, monster in self.player_monsters.items():
            if monster.evolution:
                if monster.level >= monster.evolution[1]:
                    self.evolution_queue.append((index, monster))

            # Start the first evolution if any evolutions are queued
            if self.evolution_queue and not self.evolution:
                self.start_evolution()

    def start_evolution(self):
        if self.evolution_queue:
            index, monster = self.evolution_queue.pop(0)
            self.player.block()
            self.evolution = Evolution(
                frames=self.monster_frames['monsters'],
                start_monster=monster.name,
                end_monster=monster.evolution[0],
                font=self.fonts['bold'],
                end_evolution=self.end_evolution,
                star_frames=self.star_animation_frames
            )
            self.player_monsters[index] = Monster(monster.evolution[0], monster.level)

    def end_evolution(self):
        self.evolution = None
        if self.evolution_queue:
            self.start_evolution()
        else:
            if not self.dialogue_tree:
                self.player.unblock()

    def close(self):
        self.running = False

    # settings
    def adjust_surfaces(self):
        self.tint_surf = pygame.transform.scale(self.tint_surf, (config_manager.settings['video']['window_width'],
                                                                 config_manager.settings['video']['window_height']))
        self.monster_index.adjust_surfaces()

    def adjust_fonts(self):
        screen_width, _ = self.display_surface.get_size()
        font_size_ratio = 0.015
        font_size = int(screen_width * font_size_ratio)
        self.fonts = {
            'dialogue': pygame.font.Font(join('..', 'graphics', 'fonts', 'PixeloidSans.ttf'), font_size),
            'regular': pygame.font.Font(join('..', 'graphics', 'fonts', 'PixeloidSans.ttf'), font_size),
            'small': pygame.font.Font(join('..', 'graphics', 'fonts', 'PixeloidSans.ttf'), int(font_size * 0.6)),
            'bold': pygame.font.Font(join('..', 'graphics', 'fonts', 'dogicapixelbold.otf'), font_size)
        }
        self.monster_index.adjust_fonts()

    def adjust_volume(self, category):
        for name, sound in self.audio.items():
            if name.split('_')[0] == category:
                sound.set_volume(config_manager.settings['audio'][category])

    # save/load
    def to_dict(self):
        return {
            'current_world': self.current_world,
            'player_monsters': [monster.to_dict() for monster in self.player_monsters.values()]
        }

    def from_dict(self, data):
        self.current_world = data['current_world']
        self.player_monsters = data['player_monsters']

    def save_game(self, file_name):
        characters_data = [character.to_dict() for character in self.character_sprites]
        save_data = {
            'game_data': self.to_dict(),
            'player': self.player.to_dict(),
            'characters': characters_data,
            'character_data': game_data.to_dict()
        }
        save_manager.save(save_data, file_name)

    def load_game(self, file_name, exists=True):
        if exists:
            save_data = save_manager.load(file_name)
            if save_data:
                if 'game_data' in save_data:
                    self.from_dict(save_data['game_data'])
                    if 'player_monsters' in save_data['game_data']:
                        self.player_monsters = {}
                        for i, monster_data in enumerate(save_data['game_data']['player_monsters']):
                            monster = Monster(monster_data['name'], monster_data['level'])
                            monster.from_dict(monster_data)
                            self.player_monsters[i] = monster
                if 'character_data' in save_data:
                    game_data.from_dict(save_data['character_data'])

                if 'player' in save_data:
                    # Set up the game with the loaded tmx_map
                    self.setup(self.tmx_maps[self.current_world], save_data['player']['pos'])

                    self.player.from_dict(save_data['player'])
                if 'characters' in save_data:
                    for char_data, character in zip(save_data['characters'], self.character_sprites):
                        character.from_dict(char_data)
            self.monster_index = MonsterInventory(self.player_monsters, self.fonts, self.monster_frames)

    # run function
    def show_loading_screen(self):
        loading_font = pygame.font.Font(None, 74)
        loading_text = loading_font.render('Loading...', True, (255, 255, 255))
        self.display_surface.blit(loading_text,
                                  (self.display_surface.get_width() // 2 - loading_text.get_width() // 2,
                                   self.display_surface.get_height() // 2 - loading_text.get_height() // 2))
        pygame.display.flip()

    def run(self):
        while self.running:
            dt = self.clock.tick() / 1000
            self.display_surface.fill('black')

            # event loop
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    exit()

            # update
            if self.start_up_delay.active:
                self.start_up_delay.update()

            if not self.start_up_delay.active:
                self.encounter_timer.update()
                if not self.player.blocked or self.monster_index_open:
                    self.input()
                self.transition_check()
                self.all_sprites.update(dt)
                self.check_for_monster()

                # drawing
                self.all_sprites.draw(self.player)

                # overlays
                if self.dialogue_tree:          self.dialogue_tree.update(self.evolution)
                if self.monster_index_open:     self.monster_index.update(dt)
                if self.battle:                 self.battle.update(dt)
                if self.evolution:              self.evolution.update(dt)
                if self.options_open:           self.options.run()

                self.tint_screen(dt)

            debug_str = ''
            debug(debug_str)

            pygame.display.flip()

        for audio in self.audio.values():
            audio.fadeout(500)
