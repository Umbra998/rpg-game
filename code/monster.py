from game_data import game_data


class Monster:
    def __init__(self, name, level):
        self.name = name
        self.level = level
        self.paused = True

        # stats
        self.element = game_data.monster_data[name]['stats']['element']
        self.base_stats = game_data.monster_data[name]['stats']
        self.health = self.base_stats['max_health'] * self.level
        self.energy = max(1, self.base_stats['max_energy'] * (self.level // 10))
        self.abilities = game_data.monster_data[name]['abilities']
        self.defending = False

        # experience
        self.exp = 0
        self.level_up = self.level * self.level * 150
        self.evolution = game_data.monster_data[self.name]['evolve']

    def reduce_energy(self, attack):
        self.energy -= game_data.attack_data[attack]['cost']

    def stat_limiter(self):
        self.health = max(0, min(self.health, self.get_stat('max_health')))
        self.energy = max(0, min(self.energy, self.get_stat('max_energy')))

    def update_exp(self, amount):
        if self.level != 100:
            if self.level_up - self.exp > amount:
                self.exp += amount
            else:
                self.level += 1
                self.exp = amount - (self.level_up - self.exp)
                self.level_up = self.level * self.level * 150

    # getters
    def get_stat(self, stat):
        return self.base_stats[stat] * self.level if stat != 'max_energy'\
            else max(1, self.base_stats['max_energy'] * (self.level // 10))

    def get_stats(self):
        return {
            'health': self.get_stat('max_health'),
            'energy': self.get_stat('max_energy'),
            'attack': self.get_stat('attack'),
            'power': self.get_stat('power'),
            'defense': self.get_stat('defense'),
            'speed': self.get_stat('speed'),
        }

    def get_base_damage(self, attack):
        return self.get_stat('attack') * game_data.attack_data[attack]['amount']

    def get_abilities(self, all_abilities=True):
        if all_abilities:
            return [ability for lvl, ability in self.abilities.items() if self.level >= lvl]
        else:
            return [ability for lvl, ability in self.abilities.items() if self.level >= lvl]

    def get_info(self):
        return (
            (self.health, self.get_stat('max_health')),
            (self.energy, self.get_stat('max_energy'))
        )

    # save/load
    def to_dict(self):
        return {
            'name': self.name,
            'level': self.level,
            'health': self.health,
            'abilities': self.abilities,
            'exp': self.exp
        }

    def from_dict(self, data):
        self.health = data['health']
        self.abilities = {int(k): v for k, v in data['abilities'].items()}
        self.exp = data['exp']
        self.level = data['level']
        self.name = data['name']

    def __repr__(self):
        return f"{self.name} at level {self.level}"

    # update
    def update(self):
        self.stat_limiter()
