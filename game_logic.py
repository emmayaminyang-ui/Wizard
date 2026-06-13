import random

# 定义基础花色和特殊牌常量
SUITS = ['Red', 'Blue', 'Yellow', 'Green']
SPECIALS = ['Wizard', 'Jester']

class Card:
    """卡牌类：定义单张卡牌的属性"""
    def __init__(self, card_type, suit=None, value=None):
        self.card_type = card_type  # 'Normal' (普通颜色牌), 'Wizard' (巫师), 'Jester' (小丑)
        self.suit = suit            # 花色：'Red', 'Blue', 'Yellow', 'Green' 或 None
        self.value = value          # 点数：1 到 13 或 None

    def __repr__(self):
        # 用于在控制台打印测试时，能直观看到是什么牌
        if self.card_type == 'Normal':
            return f"{self.suit}-{self.value}"
        return f"[{self.card_type}]"

class Deck:
    """牌库类：负责生成 60 张牌、洗牌、发牌和翻强花"""
    def __init__(self):
        self.cards = []
        self.build()

    def build(self):
        """生成完整的 60 张牌库"""
        self.cards = []
        # 生成 4 种花色，每种 1-13 点 [cite: 50]
        for suit in SUITS:
            for val in range(1, 14):
                self.cards.append(Card('Normal', suit, val))
        
        # 生成 4 张巫师和 4 张小丑 [cite: 50]
        for _ in range(4):
            self.cards.append(Card('Wizard'))
            self.cards.append(Card('Jester'))

    def shuffle(self):
        """洗牌：彻底打乱 60 张牌 [cite: 77]"""
        random.shuffle(self.cards)

    def deal(self, num_cards):
        """发牌：从牌堆顶抽出指定数量的牌"""
        dealt_cards = []
        for _ in range(num_cards):
            if self.cards:
                dealt_cards.append(self.cards.pop())
        return dealt_cards

    def flip_for_global_trump(self):
        """
        翻牌定强花（适用于第 1 到 14 轮）：
        从剩余牌堆顶部翻牌，遇到巫师/小丑则继续往下翻，直到翻出颜色牌 。
        """
        discard_pile = []
        trump_suit = None

        while self.cards:
            # 从牌堆顶翻开一张牌
            top_card = self.cards.pop()
            
            if top_card.card_type == 'Normal':
                # 找到颜色牌，确立本轮的全局强花 
                trump_suit = top_card.suit
                break
            else:
                # 如果是巫师或小丑，暂时放进废牌堆，继续循环 
                discard_pile.append(top_card)
        
        # 👨‍💻 安全网机制：如果运气极度极端（比如第14轮剩下4张全是特殊牌），导致牌库抽干都没颜色牌
        # 我们判定本轮为“无强花” (None) 
        
        return trump_suit

# ==========================================
# 🧪 猎魔人专属测试区（这部分代码供你理解逻辑，可随时删除）
# 模拟真实的 4 人局第 5 轮发牌
round_number = 5
player_A_hand = deck.deal(round_number)
player_B_hand = deck.deal(round_number)
player_C_hand = deck.deal(round_number)
player_D_hand = deck.deal(round_number)

print(f"3. 模拟第 {round_number} 轮发牌完毕，玩家 A 的手牌: {player_A_hand}")
print(f"   此时 4 人全部发牌完毕，牌库剩余 {len(deck.cards)} 张牌。") # 👈 这里就会完美显示剩余 40 张！

# 模拟翻牌定强花
global_trump = deck.flip_for_global_trump()
print(f"4. 命运的翻牌！本轮的全局强花是: {global_trump}")
print(f"   翻完强花后，牌库最终剩余 {len(deck.cards)} 张牌。") # 👈 这里会显示 39 张（如果遇到巫师/小丑重翻，则会少于 39 张）
# ==========================================