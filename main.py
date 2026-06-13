import fastapi
import fastapi.responses
import random
from typing import List, Dict, Set
import json

# --- 牌库与逻辑类 ---
class Card:
    def __init__(self, suit, value, display_name):
        self.suit = suit
        self.value = value
        self.display_name = display_name
    def __str__(self): return self.display_name

class Deck:
    def __init__(self):
        self.cards = []
        suits = ['红', '蓝', '黄', '绿']
        for suit in suits:
            for i in range(1, 14): self.cards.append(Card(suit, i, f"{suit}{i}"))
        for _ in range(4):
            self.cards.append(Card('特殊', 15, "巫师"))
            self.cards.append(Card('特殊', 0, "小丑"))
    def shuffle(self): random.shuffle(self.cards)
    def draw(self): return self.cards.pop() if self.cards else None

class Player:
    def __init__(self, name, seat_idx):
        self.name = name
        self.seat_idx = seat_idx
        self.hand = []
        self.prediction = 0
        self.tricks_won = 0

class GameRoom:
    def __init__(self, room_code, host_seat):
        self.room_code = room_code
        self.seats = [None] * 6             # 6个座位，None=空，否则存玩家名
        self.host_seat = host_seat          # 房主座位索引
        self.players = []                   # 游戏开始后的Player列表（按座位顺序）
        self.player_count = 0
        self.round_num = 0
        self.deck = Deck()
        self.trump_suit = None
        self.trump_card = None
        self.scores = []                    # 累计得分
        self.current_leader = 0
        self.current_turn = 0
        self.cards_in_trick = []
        self.lead_suit = None
        self.tricks_played = 0
        self.trump_decayed = False
        self.game_phase = "LOBBY"           # LOBBY / BIDDING / PLAYING / ROUND_OVER / GAME_OVER
        self.max_rounds = 0                 # 60 / 人数
        self.ready_players = set()
        self.round_history = []

    def get_player_count(self):
        return sum(1 for s in self.seats if s is not None)

    def can_start(self):
        return self.get_player_count() >= 4

    def start_game(self):
        """LOBBY -> 游戏开始，根据实际人数初始化"""
        self.player_count = self.get_player_count()
        self.max_rounds = 60 // self.player_count
        self.players = []
        for i, name in enumerate(self.seats):
            if name is not None:
                self.players.append(Player(name, i))
        self.scores = [0] * self.player_count
        self.round_num = 0
        self.round_history = []
        self.ready_players = set()
        self.game_phase = "WAITING"

    # ====== 发牌与轮次管理 ======
    def start_new_round(self):
        self.round_num += 1
        self.deck = Deck()
        self.deck.shuffle()
        self.trump_suit = None
        self.trump_card = None
        self.trump_decayed = False
        self.tricks_played = 0
        self.cards_in_trick = []
        self.lead_suit = None
        self.game_phase = "BIDDING"
        for p in self.players:
            p.hand = []
            p.prediction = 0
            p.tricks_won = 0
        # 发牌：每人发 round_num 张
        for _ in range(self.round_num):
            for p in self.players:
                p.hand.append(self.deck.draw())
        # 定强花（最后一轮牌库为空不翻）
        if self.round_num < self.max_rounds:
            while True:
                c = self.deck.draw()
                if c is None:
                    break
                if c.suit in ['红', '蓝', '黄', '绿']:
                    self.trump_suit = c.suit
                    self.trump_card = c
                    break
        else:
            self.trump_suit = None
            self.trump_card = None
        # 首发权：第一轮随机，其余沿用上轮最后一墩财家
        if self.round_num == 1:
            self.current_leader = random.randint(0, self.player_count - 1)
        self.current_turn = self.current_leader

    # ====== 核心模块一：validate_move ======
    def validate_move(self, player_idx, card):
        """检测出牌是否符合跟牌规则"""
        player = self.players[player_idx]
        # 最后一轮首墩首发者禁止打巫师/小丑
        if (self.round_num == self.max_rounds and self.tricks_played == 0
                and len(self.cards_in_trick) == 0
                and player_idx == self.current_leader
                and card.suit == '特殊'):
            return False, "最后一轮首发者必须打出基础颜色牌"
        # 巫师和小丑可以随时打出
        if card.suit == '特殊':
            return True, ""
        # 有主色必须出主色（主色由翻牌决定，非出牌者决定）
        # 次主色（lead_suit）不强制跟牌，玩家可自由出牌
        if self.trump_suit and not self.trump_decayed:
            has_trump = any(c.suit == self.trump_suit for c in player.hand if c.suit != '特殊')
            if has_trump and card.suit != self.trump_suit:
                return False, f"你有{self.trump_suit}色（主色）牌，必须跟出"
        return True, ""

    # ====== 核心模块二：determine_winner ======
    def determine_winner(self):
        """根据优先级表返回该墩赢家 player_idx"""
        # 1) 巫师：首位打出巫师者赢
        for idx, card in self.cards_in_trick:
            if card.display_name == "巫师":
                return idx
        # 2) 全部是小丑：先出者被迫吃下
        all_jesters = all(card.display_name == "小丑" for _, card in self.cards_in_trick)
        if all_jesters:
            return self.cards_in_trick[0][0]
        # 过滤掉小丑（小丑无条件放弃吃墩权）
        candidates = [(idx, card) for idx, card in self.cards_in_trick if card.display_name != "小丑"]
        # 3) 确定有效强花
        effective_trump = self.trump_suit
        if self.trump_decayed:
            effective_trump = self.lead_suit
        # 4) 强花/临时主色点数最大者赢
        if effective_trump:
            trump_cards = [(idx, card) for idx, card in candidates if card.suit == effective_trump]
            if trump_cards:
                return max(trump_cards, key=lambda x: x[1].value)[0]
        # 5) 引导花色点数最大者赢
        if self.lead_suit:
            lead_cards = [(idx, card) for idx, card in candidates if card.suit == self.lead_suit]
            if lead_cards:
                return max(lead_cards, key=lambda x: x[1].value)[0]
        # 6) 安全回退
        return candidates[0][0]

    # ====== 核心模块三：auto_trump_decay ======
    def auto_trump_decay(self):
        """监听所有玩家手牌，一旦强花清零自动重置"""
        if self.trump_suit is None or self.trump_decayed:
            return
        for p in self.players:
            for c in p.hand:
                if c.suit == self.trump_suit:
                    return
        self.trump_decayed = True
        self.trump_suit = None

    # ====== 出牌流程 ======
    def play_card(self, player_idx, card_index):
        """处理一张出牌，返回结果字典"""
        player = self.players[player_idx]
        if card_index < 0 or card_index >= len(player.hand):
            return {"type": "PLAY_INVALID", "msg": "无效牌索引"}
        card = player.hand[card_index]
        valid, msg = self.validate_move(player_idx, card)
        if not valid:
            return {"type": "PLAY_INVALID", "msg": msg}
        player.hand.pop(card_index)
        # 设置引导花色（第一张非特殊牌定色）
        if self.lead_suit is None and card.suit != '特殊':
            self.lead_suit = card.suit
            if self.round_num == self.max_rounds and self.tricks_played == 0:
                self.trump_suit = card.suit
        self.cards_in_trick.append((player_idx, card))
        # 判断本墩是否完成（4人都出了）
        if len(self.cards_in_trick) == self.player_count:
            winner = self.determine_winner()
            self.players[winner].tricks_won += 1
            self.tricks_played += 1
            trick_result = {
                "type": "TRICK_RESULT",
                "winner": winner,
                "winner_name": self.players[winner].name,
                "cards": [(idx, str(c)) for idx, c in self.cards_in_trick],
                "tricks_played": self.tricks_played,
                "trump_suit": self.trump_suit,
                "trump_decayed": self.trump_decayed,
                "players": [
                    {"name": p.name, "prediction": p.prediction,
                     "tricks_won": p.tricks_won,
                     "hand": [str(c) for c in p.hand]}
                    for p in self.players
                ]
            }
            self.current_leader = winner
            self.current_turn = winner
            self.cards_in_trick = []
            self.lead_suit = None
            # 墩结束后再检测强花衰退（确保本墩内主色判定稳定）
            self.auto_trump_decay()
            if self.tricks_played == self.round_num:
                round_scores = self.calculate_scores()
                trick_result["round_over"] = True
                trick_result["round_scores"] = round_scores
                trick_result["total_scores"] = self.scores
                trick_result["round_history"] = self.round_history
                # 判断是否整局结束（15轮打完）
                if self.round_num >= self.max_rounds:
                    self.game_phase = "GAME_OVER"
                    trick_result["game_over"] = True
                else:
                    self.game_phase = "ROUND_OVER"
                    trick_result["game_over"] = False
            else:
                trick_result["round_over"] = False
                trick_result["next_turn"] = self.current_turn
            return trick_result
        else:
            self.current_turn = (self.current_turn + 1) % self.player_count
            return {
                "type": "PLAY_OK",
                "card_played": str(card),
                "player_idx": player_idx,
                "next_turn": self.current_turn,
                "cards_in_trick": [(idx, str(c)) for idx, c in self.cards_in_trick],
                "lead_suit": self.lead_suit,
                "trump_suit": self.trump_suit,
                "trump_decayed": self.trump_decayed
            }

    # ====== 计分逻辑 ======
    def calculate_scores(self):
        """精准命中 +20+(tricks×10)，预测破产 -10×|差值|"""
        round_scores = []
        for i, p in enumerate(self.players):
            if p.tricks_won == p.prediction:
                score = 20 + p.tricks_won * 10
            else:
                score = -10 * abs(p.tricks_won - p.prediction)
            self.scores[i] += score
            round_scores.append(score)
        # 记录本轮历史
        self.round_history.append({
            "round": self.round_num,
            "scores": round_scores,
            "predictions": [p.prediction for p in self.players],
            "tricks": [p.tricks_won for p in self.players]
        })
        return round_scores

    # ====== 状态快照（每个玩家只能看到自己的手牌） ======
    def get_state_for_player(self, viewer_idx):
        """viewer_idx: 查看者的玩家索引，只暴露自己的手牌"""
        players_data = []
        for i, p in enumerate(self.players):
            if i == viewer_idx:
                players_data.append({
                    "name": p.name, "prediction": p.prediction,
                    "tricks_won": p.tricks_won,
                    "hand": [str(c) for c in p.hand],
                    "card_count": len(p.hand)
                })
            else:
                players_data.append({
                    "name": p.name, "prediction": p.prediction,
                    "tricks_won": p.tricks_won,
                    "hand": [],  # 不暴露他人手牌
                    "card_count": len(p.hand)
                })
        return {
            "round": self.round_num,
            "phase": self.game_phase,
            "trump": {
                "suit": self.trump_suit,
                "display": self.trump_card.display_name if self.trump_card else "无",
                "decayed": self.trump_decayed
            },
            "current_turn": self.current_turn,
            "current_leader": self.current_leader,
            "tricks_played": self.tricks_played,
            "scores": self.scores,
            "players": players_data
        }

# ====== 房间管理 ======
rooms: Dict[str, GameRoom] = {}
room_connections: Dict[str, Dict[int, fastapi.WebSocket]] = {}  # room_code -> {seat_idx: ws}

app = fastapi.FastAPI()

@app.get("/")
async def get(): return fastapi.responses.FileResponse('index.html')

async def broadcast(room_code, message):
    """广播相同消息给房间内所有连接"""
    if room_code in room_connections:
        msg_str = json.dumps(message)
        for ws in room_connections[room_code].values():
            try:
                await ws.send_text(msg_str)
            except:
                pass

async def broadcast_personal(room_code, room):
    """发牌后给每个玩家发送个人化状态（只能看到自己的牌）"""
    if room_code not in room_connections:
        return
    for seat_idx, ws in room_connections[room_code].items():
        # 找到该座位对应的 player_idx
        player_idx = -1
        for i, p in enumerate(room.players):
            if p.seat_idx == seat_idx:
                player_idx = i
                break
        if player_idx < 0:
            continue
        state = room.get_state_for_player(player_idx)
        state["type"] = "DEAL_RESULT"
        state["my_player_idx"] = player_idx
        try:
            await ws.send_text(json.dumps(state))
        except:
            pass

async def broadcast_with_hands(room_code, room, base_message):
    """墩结果等需要更新手牌的消息，每人只看到自己的牌"""
    if room_code not in room_connections:
        return
    for seat_idx, ws in room_connections[room_code].items():
        player_idx = -1
        for i, p in enumerate(room.players):
            if p.seat_idx == seat_idx:
                player_idx = i
                break
        if player_idx < 0:
            continue
        msg = dict(base_message)
        # 替换 players 字段为个人化版本
        if "players" in msg:
            personal_players = []
            for i, p in enumerate(room.players):
                if i == player_idx:
                    personal_players.append({"name": p.name, "prediction": p.prediction,
                        "tricks_won": p.tricks_won, "hand": [str(c) for c in p.hand], "card_count": len(p.hand)})
                else:
                    personal_players.append({"name": p.name, "prediction": p.prediction,
                        "tricks_won": p.tricks_won, "hand": [], "card_count": len(p.hand)})
            msg["players"] = personal_players
        msg["my_player_idx"] = player_idx
        try:
            await ws.send_text(json.dumps(msg))
        except:
            pass

@app.websocket("/ws")
async def websocket_endpoint(websocket: fastapi.WebSocket):
    await websocket.accept()
    current_room = None
    my_seat = -1
    try:
      while True:
        data = await websocket.receive_text()
        msg = json.loads(data)
        msg_type = msg.get("type")

        # === 创建房间 ===
        if msg_type == "CREATE_ROOM":
            room_code = msg.get("room_code", "").strip()
            seat_idx = msg.get("seat_idx", 0)
            player_name = msg.get("name", "Player")
            if room_code in rooms:
                await websocket.send_text(json.dumps({"type": "ERROR", "msg": "房间已存在"}))
                continue
            room = GameRoom(room_code, seat_idx)
            room.seats[seat_idx] = player_name
            rooms[room_code] = room
            room_connections[room_code] = {seat_idx: websocket}
            current_room = room_code
            my_seat = seat_idx
            await websocket.send_text(json.dumps({
                "type": "ROOM_JOINED",
                "room_code": room_code,
                "seats": room.seats,
                "host_seat": room.host_seat,
                "my_seat": my_seat
            }))

        # === 加入房间 ===
        elif msg_type == "JOIN_ROOM":
            room_code = msg.get("room_code", "").strip()
            seat_idx = msg.get("seat_idx", -1)
            player_name = msg.get("name", "Player")
            if room_code not in rooms:
                await websocket.send_text(json.dumps({"type": "ERROR", "msg": "房间不存在"}))
                continue
            room = rooms[room_code]
            if room.get_player_count() >= 6:
                await websocket.send_text(json.dumps({"type": "ERROR", "msg": "房间已满"}))
                continue
            if seat_idx < 0 or seat_idx > 5 or room.seats[seat_idx] is not None:
                await websocket.send_text(json.dumps({"type": "ERROR", "msg": "座位已被占"}))
                continue
            room.seats[seat_idx] = player_name
            room_connections[room_code][seat_idx] = websocket
            current_room = room_code
            my_seat = seat_idx
            await websocket.send_text(json.dumps({
                "type": "ROOM_JOINED",
                "room_code": room_code,
                "seats": room.seats,
                "host_seat": room.host_seat,
                "my_seat": my_seat
            }))
            # 广播座位更新
            await broadcast(room_code, {
                "type": "SEATS_UPDATE",
                "seats": room.seats,
                "can_start": room.can_start()
            })

        # === 开始游戏（仅房主） ===
        elif msg_type == "START_GAME":
            if not current_room or current_room not in rooms:
                continue
            room = rooms[current_room]
            if my_seat != room.host_seat:
                await websocket.send_text(json.dumps({"type": "ERROR", "msg": "只有房主可以开始游戏"}))
                continue
            if not room.can_start():
                await websocket.send_text(json.dumps({"type": "ERROR", "msg": "至少需要4人才能开始"}))
                continue
            room.start_game()
            await broadcast(current_room, {
                "type": "GAME_STARTED",
                "player_count": room.player_count,
                "max_rounds": room.max_rounds,
                "players": [{"name": p.name, "seat_idx": p.seat_idx} for p in room.players]
            })

        # === 发牌（每人只收到自己的手牌） ===
        elif msg_type == "DEAL":
            if not current_room or current_room not in rooms:
                continue
            room = rooms[current_room]
            room.start_new_round()
            await broadcast_personal(current_room, room)

        # === 报墩 ===
        elif msg_type == "BID":
            if not current_room:
                continue
            room = rooms[current_room]
            p_idx = msg.get("player_idx")
            bid_value = msg.get("value")
            room.players[p_idx].prediction = bid_value
            await broadcast(current_room, {
                "type": "BID_CONFIRMED",
                "player_idx": p_idx,
                "value": bid_value,
                "msg": f"{room.players[p_idx].name}预测赢{bid_value}墩"
            })

        elif msg_type == "BID_DONE":
            if not current_room:
                continue
            room = rooms[current_room]
            room.game_phase = "PLAYING"
            await broadcast(current_room, {
                "type": "PLAY_START",
                "current_turn": room.current_turn,
                "msg": f"请{room.players[room.current_turn].name}首发出牌"
            })

        # === 出牌 ===
        elif msg_type == "PLAY":
            if not current_room:
                continue
            room = rooms[current_room]
            p_idx = msg.get("player_idx")
            card_idx = msg.get("card_index")
            if p_idx != room.current_turn:
                await websocket.send_text(json.dumps({
                    "type": "PLAY_INVALID",
                    "msg": f"当前轮到{room.players[room.current_turn].name}"
                }))
                continue
            result = room.play_card(p_idx, card_idx)
            # 墩结果包含 players 手牌信息时，个人化发送
            if result.get("type") == "TRICK_RESULT" and "players" in result:
                await broadcast_with_hands(current_room, room, result)
            else:
                await broadcast(current_room, result)

        # === 再来一局 ===
        elif msg_type == "READY":
            if not current_room:
                continue
            room = rooms[current_room]
            p_idx = msg.get("player_idx")
            if p_idx in room.ready_players:
                room.ready_players.discard(p_idx)
            else:
                room.ready_players.add(p_idx)
            await broadcast(current_room, {
                "type": "READY_UPDATE",
                "ready_players": list(room.ready_players)
            })
            if len(room.ready_players) == room.player_count:
                room.round_num = 0
                room.scores = [0] * room.player_count
                room.round_history = []
                room.ready_players = set()
                room.game_phase = "WAITING"
                await broadcast(current_room, {"type": "GAME_RESTART"})

        # === 离开房间 ===
        elif msg_type == "LEAVE":
            if current_room and current_room in rooms:
                room = rooms[current_room]
                room.seats[my_seat] = None
                if current_room in room_connections:
                    room_connections[current_room] = {k: v for k, v in room_connections[current_room].items() if v != websocket}
                await broadcast(current_room, {
                    "type": "SEATS_UPDATE",
                    "seats": room.seats,
                    "can_start": room.can_start()
                })
                # 房间没人了就删除
                if room.get_player_count() == 0:
                    del rooms[current_room]
                    if current_room in room_connections:
                        del room_connections[current_room]
                current_room = None
    except Exception:
        # 连接断开时清理
        if current_room and current_room in rooms:
            room = rooms[current_room]
            if 0 <= my_seat < 6:
                room.seats[my_seat] = None
            if current_room in room_connections:
                room_connections[current_room] = {k: v for k, v in room_connections[current_room].items() if v != websocket}
            try:
                await broadcast(current_room, {
                    "type": "SEATS_UPDATE",
                    "seats": room.seats,
                    "can_start": room.can_start()
                })
            except:
                pass
            if room.get_player_count() == 0:
                del rooms[current_room]
                if current_room in room_connections:
                    del room_connections[current_room]

# Server ready
print(f"Wizard Server ready. Rooms: {len(rooms)}")
