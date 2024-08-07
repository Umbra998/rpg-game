from settings import *
from config_manager import config_manager
from support import import_image
from entities import Entity


class AllSprites(pygame.sprite.Group):
    def __init__(self, collision_sprites):
        super().__init__()
        self.display_surface = pygame.display.get_surface()
        self.offset = vector()
        self.shadow_surf = import_image('..', 'graphics', 'other', 'shadow')
        self.notice_surf = import_image('..', 'graphics', 'ui', 'notice')
        self.collision_sprites = collision_sprites

    def draw(self, player):
        window_width = config_manager.settings['video']['window_width']
        window_height = config_manager.settings['video']['window_height']

        self.offset.x = -(player.rect.centerx - window_width / 2)
        self.offset.y = -(player.rect.centery - window_height / 2)

        # Define the visible area (viewport) based on the player's position
        visible_area = pygame.Rect(
            player.rect.centerx - window_width / 2,
            player.rect.centery - window_height / 2,
            window_width,
            window_height
        )

        bg_sprites = [sprite for sprite in self if sprite.z < WORLD_LAYERS['main']]
        main_sprites = sorted([sprite for sprite in self if sprite.z == WORLD_LAYERS['main']],
                              key=lambda sprite: sprite.y_sort)
        fg_sprites = [sprite for sprite in self if sprite.z > WORLD_LAYERS['main']]

        for layer in (bg_sprites, main_sprites, fg_sprites):
            for sprite in layer:
                # Check if the sprite is within the visible area
                if sprite.rect.colliderect(visible_area):
                    if isinstance(sprite, Entity):
                        self.display_surface.blit(self.shadow_surf, sprite.rect.topleft + self.offset + vector(40, 108))
                    self.display_surface.blit(sprite.image, sprite.rect.topleft + self.offset)
                    if sprite == player and player.noticed:
                        rect = self.notice_surf.get_rect(midbottom=sprite.rect.midtop)
                        self.display_surface.blit(self.notice_surf, rect.topleft + self.offset)

        # Draw hitboxes for all sprites in collision_sprites and for player
        if config_manager.settings['show_hitbox']:
            for sprite in self.collision_sprites:
                if hasattr(sprite, 'hitbox') and sprite.hitbox.colliderect(visible_area):
                    hitbox_copy = sprite.hitbox.copy()
                    hitbox_surf = pygame.Surface((int(hitbox_copy.width), int(hitbox_copy.height)), pygame.SRCALPHA)
                    hitbox_surf.fill((255, 0, 0, 128))  # Semi-transparent red for visibility
                    hitbox_rect = hitbox_copy.move(self.offset)  # Move the hitbox by the offset
                    self.display_surface.blit(hitbox_surf, hitbox_rect.topleft)
            for sprite in self:
                if sprite == player:
                    hitbox_copy = sprite.hitbox.copy()
                    hitbox_surf = pygame.Surface((int(hitbox_copy.width), int(hitbox_copy.height)), pygame.SRCALPHA)
                    hitbox_surf.fill((255, 0, 0, 128))  # Semi-transparent red for visibility
                    hitbox_rect = hitbox_copy.move(self.offset)  # Move the hitbox by the offset
                    self.display_surface.blit(hitbox_surf, hitbox_rect.topleft)
                    break


class BattleSprites(pygame.sprite.Group):
    def __init__(self):
        super().__init__()
        self.display_surface = pygame.display.get_surface()

    def draw_sprites(self, current_monster_sprite, side, mode, target_index, player_sprites, opponent_sprites):
        # get available options
        sprite_group = opponent_sprites if side == 'opponent' else player_sprites
        sprites = {sprite.pos_index: sprite for sprite in sprite_group}
        monster_sprite = sprites[list(sprites.keys())[target_index]] if sprites else None

        for sprite in sorted(self, key=lambda sprite: sprite.z):
            if not sprite.z == BATTLE_LAYERS['outline']:
                self.display_surface.blit(sprite.image, sprite.rect)
            else:
                if sprite.monster_sprite == current_monster_sprite or sprite.monster_sprite == monster_sprite\
                    and sprite.monster_sprite.entity == side\
                    and mode\
                        and mode == 'target':
                    self.display_surface.blit(sprite.image, sprite.rect)
