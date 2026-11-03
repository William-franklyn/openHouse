// Mirrors the backend's response shapes exactly (see backend/app/main.py).

export type JoinPolicy = "open" | "approval" | "invite_only";
export type InviteBy = "admins" | "members";
export type MemberRole = "owner" | "mod" | "member";
export type MemberStatus = "pending" | "active" | "left" | "removed" | "banned";

export interface RoomPublic {
  id: string;
  name: string;
  code: string;
  member_count: number;
  join_policy: JoinPolicy;
  invite_by: InviteBy | null;
  is_active: boolean;
  // True if the owner restricted joining to people on their current
  // Wi-Fi/hotspot (see RoomSettingsPanel). Never carries the actual IP.
  local_mode: boolean;
}

export interface MemberOut {
  member_id: string;
  name: string;
  is_anonymous: boolean;
  role: MemberRole;
  status: MemberStatus;
}

export interface ChannelOut {
  id: string;
  name: string;
}

export interface MessageReactionSummary {
  emoji: string;
  member_ids: string[];
}

export interface MessageOut {
  id: string;
  channel_id: string;
  seq: number;
  member_id: string | null;
  from_name: string | null;
  kind: "text" | "file" | "system";
  text: string | null;
  file_id: string | null;
  created_at: string;
  reactions: MessageReactionSummary[];
}

export interface CreateRoomResponse {
  room: RoomPublic;
  member: MemberOut;
  session_token: string;
  recovery_code: string;
}

export interface JoinResponse {
  member_id: string;
  room_id: string;
  session_token: string;
  status: MemberStatus;
}

export interface RecoverResponse {
  member: MemberOut;
  session_token: string;
}

export interface RoomDetail {
  room: RoomPublic;
  my_role: MemberRole;
  my_member_id: string;
  channels: ChannelOut[];
  video_room_token: string;
}

export interface InviteCreated {
  code: string;
  expires_at: string;
}

export interface HistoryResponse {
  messages: MessageOut[];
}

export interface UploadResponse {
  file_id: string;
  filename: string;
  size: number;
}

export interface DownloadResponse {
  url: string;
  filename: string;
  size: number;
  expires_in: number;
}

export interface ReportResponse {
  report_id: string;
  status: "open" | "done";
}

export interface AdminReport {
  id: string;
  room_id: string;
  reporter_member_id: string;
  target_member_id: string | null;
  message_id: string | null;
  reason: string;
  status: "open" | "done";
  created_at: string;
}

export interface AdminMetricRow {
  day: string;
  name: string;
  value: number;
}

// ---- WebSocket event payloads (server -> client) ----

export interface WSReady {
  type: "ready";
}

export interface WSMessage {
  type: "message";
  channel_id: string;
  id: string;
  seq: number;
  member_id: string | null;
  from_name: string | null;
  kind: "text" | "file" | "system";
  text: string | null;
  file_id: string | null;
  client_id: string | null;
  created_at: string;
}

export interface WSMessageDeleted {
  type: "message_deleted";
  channel_id: string;
  message_id: string;
}

export interface WSPins {
  type: "pins";
  message_ids: string[];
}

export interface WSReaction {
  type: "reaction";
  channel_id: string;
  message_id: string;
  emoji: string;
  member_id: string;
  added: boolean;
}

export interface PresenceMember {
  member_id: string;
  name: string;
  role: MemberRole;
}

export interface WSPresence {
  type: "presence";
  online: PresenceMember[];
}

export interface WSMemberJoined {
  type: "member_joined";
  member_id: string;
  name: string;
}

export interface WSMemberLeft {
  type: "member_left";
  member_id: string;
}

export interface WSRoleChanged {
  type: "role_changed";
  member_id: string;
  role: MemberRole;
}

export interface WSOwnershipOffer {
  type: "ownership_offer";
  from_name: string;
}

export interface WSOwnershipChanged {
  type: "ownership_changed";
  new_owner_id: string;
  message: string;
}

export interface WSChannelCreated {
  type: "channel_created";
  channel_id: string;
  name: string;
}

export interface WSRemoved {
  type: "removed";
  reason: string;
}

export interface WSRoomDeleted {
  type: "room_deleted";
  message: string;
}

export interface WSRoomEnded {
  type: "room_ended";
  message?: string;
}

export interface WSError {
  type: "error";
  code: string;
  message: string;
}

export interface WSMusicStarted {
  type: "music_started";
  id: string;
  source: "upload" | "library";
  file_id?: string;
  url?: string;
  attribution?: string;
  filename: string;
  started_by_member_id: string;
  started_by_name: string;
  started_at_ms: number;
}

export interface WSMusicStopped {
  type: "music_stopped";
}

export interface QueuedMusicTrack {
  id: string;
  source: "upload" | "library";
  file_id?: string;
  url?: string;
  attribution?: string;
  filename: string;
  requested_by_member_id: string;
  requested_by_name: string;
  queued_at_ms: number;
}

export interface WSMusicQueueUpdated {
  type: "music_queue_updated";
  queue: QueuedMusicTrack[];
}

export interface WSMusicRequested {
  type: "music_requested";
  filename: string;
  requested_by_member_id: string;
  requested_by_name: string;
}

export interface MusicLibraryTrack {
  id: string;
  title: string;
  artist: string;
  license: string;
  license_url: string;
  url: string;
}

export interface MusicLibraryResponse {
  tracks: MusicLibraryTrack[];
}

// ---- Video call: self-hosted WebRTC only. A "call" is an invite-based
// meeting identified by call_id, not an ambient room-wide thing - two
// members separately clicking a generic "join" button had no guarantee
// they'd land in the same meeting, which is exactly what call_id fixes. ----

export interface IceServersResponse {
  iceServers: RTCIceServer[];
}

export interface WSCallPresence {
  type: "call_presence";
  call_id: string;
  member_ids: string[];
}

export interface WSCallInvite {
  type: "call_invite";
  call_id: string;
  host_member_id: string;
  host_name: string;
}

export interface WSCallOffer {
  type: "call_offer";
  from_member_id: string;
  sdp: RTCSessionDescriptionInit;
}

export interface WSCallAnswer {
  type: "call_answer";
  from_member_id: string;
  sdp: RTCSessionDescriptionInit;
}

export interface WSIceCandidate {
  type: "ice_candidate";
  from_member_id: string;
  candidate: RTCIceCandidateInit;
}

export type CallSignalEvent = WSCallOffer | WSCallAnswer | WSIceCandidate;

// ---- Photo Wall: every image shared as a chat message, room-wide ----

export interface RoomPhoto {
  file_id: string;
  message_id: string;
  filename: string;
  member_id: string | null;
  member_name: string | null;
  created_at: string;
}

export interface RoomPhotosResponse {
  photos: RoomPhoto[];
}

export interface WSPhotoShared {
  type: "photo_shared";
  file_id: string;
  message_id: string;
  filename: string;
  member_id: string;
  member_name: string;
  created_at: string;
}

// ---- Games: chess is the first. One pending-or-active game per member
// per room at a time (enforced server-side) - the frontend only ever
// needs a single myGameId slot, same shape as myCallId. ----

export type GameKind =
  | "chess"
  | "tictactoe"
  | "connect4"
  | "dots_and_boxes"
  | "reversi"
  | "checkers"
  | "backgammon"
  | "battleship";
export type GameStatus = "pending" | "awaiting" | "active" | "finished";
export type GameResult = "white" | "black" | "draw";

export interface WSGameInvite {
  type: "game_invite";
  game_id: string;
  kind: GameKind;
  challenger_member_id: string;
  challenger_name: string;
  opponent_member_id: string;
  opponent_name: string;
}

// A shareable link-challenge - no opponent picked yet, anyone who opens
// the link (and isn't the creator) can claim the open seat.
export interface WSGameLinkWaiting {
  type: "game_link_waiting";
  game_id: string;
  kind: GameKind;
  white_member_id: string;
  white_name: string;
  link_token: string;
}

export interface WSGameDeclined {
  type: "game_declined";
  game_id: string;
}

export interface WSGameCancelled {
  type: "game_cancelled";
  game_id: string;
}

interface WSGameStateBase {
  type: "game_state";
  game_id: string;
  status: GameStatus;
  white_member_id: string;
  white_name: string;
  black_member_id: string;
  black_name: string;
  moves: unknown[];
  turn: "white" | "black";
  game_over: boolean;
  result: GameResult | null;
  termination: string | null;
  last_move: unknown | null;
}

export interface WSChessState extends WSGameStateBase {
  kind: "chess";
  board_fen: string;
  legal_moves: string[];
  in_check: boolean;
  last_move_was_capture: boolean;
}

export interface WSTicTacToeState extends WSGameStateBase {
  kind: "tictactoe";
  board: (0 | 1 | null)[];
}

export interface WSConnect4State extends WSGameStateBase {
  kind: "connect4";
  board: (0 | 1 | null)[][];
  legal_moves: { column: number }[];
}

export interface WSDotsAndBoxesState extends WSGameStateBase {
  kind: "dots_and_boxes";
  h_edges: boolean[][];
  v_edges: boolean[][];
  boxes: (0 | 1 | null)[][];
}

export interface WSReversiState extends WSGameStateBase {
  kind: "reversi";
  board: (0 | 1 | null)[][];
  legal_moves: { row: number; col: number }[];
}

export interface WSCheckersState extends WSGameStateBase {
  kind: "checkers";
  board: (string | null)[][];
  must_continue_from: [number, number] | null;
  legal_moves: { from: [number, number]; to: [number, number] }[];
}

export interface WSBackgammonState extends WSGameStateBase {
  kind: "backgammon";
  points: number[];
  bar: [number, number];
  borne_off: [number, number];
  dice: number[];
  remaining_dice: number[];
  legal_moves: { from: number; to: number }[];
}

// A single cell's visible value - "ship"/"empty" only ever appear on a
// viewer's own grid; the opponent's grid only ever shows hit/miss/unknown,
// regardless of what's actually underneath an unshot cell (see the
// backend's redact_for_viewer - this is the one game kind with real
// hidden per-player information).
export type BattleshipCell = "ship" | "hit" | "miss" | "empty" | "unknown";

export interface WSBattleshipState extends WSGameStateBase {
  kind: "battleship";
  white_grid: BattleshipCell[][];
  black_grid: BattleshipCell[][];
  ship_hits: [number[], number[]];
  ship_sizes: number[];
}

export type WSGameState =
  | WSChessState
  | WSTicTacToeState
  | WSConnect4State
  | WSDotsAndBoxesState
  | WSReversiState
  | WSCheckersState
  | WSBackgammonState
  | WSBattleshipState;

// A lightweight room-wide "X vs Y is live" announcement - no board state,
// just enough for a non-player's banner. watch_game is what actually
// fetches the full board (as a WSGameState sent directly to the watcher).
export interface WSGameLive {
  type: "game_live";
  game_id: string;
  kind: GameKind;
  white_member_id: string;
  white_name: string;
  black_member_id: string;
  black_name: string;
}

export interface WSGameLiveEnded {
  type: "game_live_ended";
  game_id: string;
}

export interface WSGameWatchers {
  type: "game_watchers";
  game_id: string;
  count: number;
}

export interface LeaderboardRow {
  member_id: string;
  name: string;
  wins: number;
  losses: number;
  draws: number;
  games_played: number;
}

export interface LeaderboardResponse {
  rows: LeaderboardRow[];
}

// ---- Party games: trivia is the first. N arbitrary room participants in
// a host-started lobby, not the 2-seat board-game model above - a
// genuinely separate type, not a GameKind. One live party game per room
// at a time (enforced server-side). ----

export type PartyGameKind =
  | "trivia"
  | "draft"
  | "uno"
  | "codenames"
  | "hearts"
  | "werewolf"
  | "spades"
  | "buzzer"
  | "drawing";
export type PartyGameStatus = "lobby" | "active" | "finished" | "cancelled";
export type PartyRoundPhase =
  | "lobby"
  | "question"
  | "reveal"
  | "picking"
  | "scoring_round_over"
  | "turn"
  | "hand_over"
  | "clue"
  | "guessing"
  | "passing"
  | "trick"
  | "night_actions"
  | "day_vote"
  | "bidding"
  | "buzzing"
  | "answering"
  | "drawing";

export interface PartyScoreRow {
  member_id: string;
  name: string;
  score: number;
  round_points: number | null;
  answered: boolean;
  // Codenames-only: present on every row when kind === "codenames".
  team?: "red" | "blue" | "team_a" | "team_b";
  is_spymaster?: boolean;
}

export interface TriviaQuestionPublic {
  id: string;
  category: string;
  question: string;
  choices: string[];
}

export interface TriviaQuestionRevealed extends TriviaQuestionPublic {
  correct_index: number;
}

interface WSPartyStateBase {
  type: "party_state";
  party_game_id: string;
  kind: PartyGameKind;
  status: PartyGameStatus;
  host_member_id: string;
  round_index: number;
  total_rounds: number;
  participant_ids: string[];
  scoreboard: PartyScoreRow[];
  phase: PartyRoundPhase;
}

export interface WSPartyLobbyState extends WSPartyStateBase {
  phase: "lobby";
}

export interface WSTriviaQuestionState extends WSPartyStateBase {
  kind: "trivia";
  phase: "question";
  question: TriviaQuestionPublic;
  round_started_at_ms: number;
  round_deadline_ms: number;
  answered_member_ids: string[];
  my_answer: { choice_index: number } | null;
}

export interface WSTriviaRevealState extends WSPartyStateBase {
  kind: "trivia";
  phase: "reveal";
  question: TriviaQuestionRevealed;
  answers: Record<string, { choice_index: number; answered_at_ms: number }>;
  round_points_awarded: Record<string, number>;
}

// ---- Draft (card draft): pick-and-pass hands, set-collection scoring.
// Built as a PartyEngine (not CardEngine) - N participants in lockstep
// rounds, no persistent chip stack, see the backend's draft_engine.py. ----

export interface DraftCard {
  id: string;
  color: string;
  value: number;
}

export interface DraftRoundResult {
  collected: DraftCard[];
  score: number;
  colors: Record<string, number>;
}

interface WSDraftStateBase extends WSPartyStateBase {
  kind: "draft";
  scoring_round: number;
  num_scoring_rounds: number;
  pick_in_round: number;
  hand_size: number;
}

export interface WSDraftPickingState extends WSDraftStateBase {
  phase: "picking";
  my_hand: DraftCard[] | null;
  my_pick: DraftCard | null;
  my_collected: DraftCard[] | null;
  picked_member_ids: string[];
  collected_counts: Record<string, number>;
}

export interface WSDraftRevealState extends WSDraftStateBase {
  phase: "reveal";
  my_hand: DraftCard[] | null;
  my_pick: DraftCard | null;
  my_collected: DraftCard[] | null;
  picked_member_ids: string[];
  collected_counts: Record<string, number>;
  revealed_picks: Record<string, DraftCard>;
}

export interface WSDraftScoringRoundOverState extends WSDraftStateBase {
  phase: "scoring_round_over";
  round_results: Record<string, DraftRoundResult>;
}

// ---- Uno: strict turn rotation, not simultaneous like Trivia/Draft - a
// "round" here means "one player's turn." Built as a PartyEngine anyway,
// see the backend's uno_engine.py docstring for why. ----

export type UnoColor = "Red" | "Blue" | "Green" | "Yellow" | "Wild";
export type UnoCardKind = "number" | "skip" | "reverse" | "draw2" | "wild" | "wild_draw4";

export interface UnoCard {
  id: string;
  color: UnoColor;
  kind: UnoCardKind;
  value: number | null;
}

export interface UnoHandResult {
  winner_member_id: string;
  points: number;
  hand_sizes: Record<string, number>;
}

export interface UnoLastAction {
  member_id: string;
  kind: "draw" | "play";
  card: UnoCard | null;
}

interface WSUnoStateBase extends WSPartyStateBase {
  kind: "uno";
  hand_number: number;
  num_hands: number;
}

export interface WSUnoTurnState extends WSUnoStateBase {
  phase: "turn";
  my_hand: UnoCard[] | null;
  hand_sizes: Record<string, number>;
  discard_top: UnoCard | null;
  active_color: UnoColor | null;
  direction: 1 | -1;
  current_player_id: string;
  draw_pile_size: number;
  last_action: null;
}

export interface WSUnoRevealState extends WSUnoStateBase {
  phase: "reveal";
  my_hand: UnoCard[] | null;
  hand_sizes: Record<string, number>;
  discard_top: UnoCard | null;
  active_color: UnoColor | null;
  direction: 1 | -1;
  current_player_id: string;
  draw_pile_size: number;
  last_action: UnoLastAction;
}

export interface WSUnoHandOverState extends WSUnoStateBase {
  phase: "hand_over";
  hand_result: UnoHandResult | null;
}

// ---- Codenames: two teams (red/blue), each with one spymaster (full
// board visibility) and N operatives (only revealed owners visible).
// Built as a PartyEngine by treating a "round" as one atomic action - a
// clue or a single guess/pass - see the backend's codenames_engine.py. ----

export type CodenamesTeam = "red" | "blue";
export type CodenamesCardOwner = "red" | "blue" | "neutral" | "assassin";

export interface CodenamesCard {
  id: string;
  word: string;
  revealed: boolean;
  owner: CodenamesCardOwner | null;
}

export interface CodenamesTeamRoster {
  spymaster: string;
  operatives: string[];
}

export interface CodenamesClue {
  word: string;
  number: number;
}

export interface CodenamesLastEvent {
  kind: "clue_given" | "clue_timeout" | "guess_result" | "guess_pass" | "guess_timeout";
  team: CodenamesTeam;
  word?: string;
  number?: number;
  owner?: CodenamesCardOwner;
}

interface WSCodenamesStateBase extends WSPartyStateBase {
  kind: "codenames";
  teams: Record<CodenamesTeam, CodenamesTeamRoster>;
  board: CodenamesCard[];
  active_team: CodenamesTeam;
  my_team: CodenamesTeam | null;
  my_role: "spymaster" | "operative" | null;
  current_clue: CodenamesClue | null;
  guesses_remaining: number | null;
  winner: CodenamesTeam | null;
  win_reason: "all_words_found" | "assassin_hit" | null;
}

export interface WSCodenamesClueState extends WSCodenamesStateBase {
  phase: "clue";
  last_event: null;
}

export interface WSCodenamesGuessingState extends WSCodenamesStateBase {
  phase: "guessing";
  last_event: null;
}

export interface WSCodenamesRevealState extends WSCodenamesStateBase {
  phase: "reveal";
  last_event: CodenamesLastEvent;
}

// ---- Hearts: strictly 4 players, two round shapes interleaved within
// one hand - a simultaneous "passing" round (everyone submits 3 cards
// independently, like Trivia) and a single-actor "trick" round (like
// Uno's one-turn-per-round reinterpretation). See hearts_engine.py. ----

export type HeartsSuit = "C" | "D" | "H" | "S";
export type HeartsPassDirection = "left" | "right" | "across" | "hold";

export interface HeartsCard {
  id: string;
  suit: HeartsSuit;
  rank: number;
}

export interface HeartsTrickEntry {
  member_id: string;
  card: HeartsCard;
}

export interface HeartsLastEvent {
  kind: "cards_passed" | "card_played" | "trick_won";
  direction?: HeartsPassDirection;
  member_id?: string;
  card?: HeartsCard;
  cards?: HeartsCard[];
}

interface WSHeartsStateBase extends WSPartyStateBase {
  kind: "hearts";
  hand_number: number;
  pass_direction: HeartsPassDirection | null;
  pass_to_member_id: string | null;
  my_hand: HeartsCard[] | null;
  hand_sizes: Record<string, number>;
  have_passed: boolean;
  current_trick: HeartsTrickEntry[];
  lead_suit: HeartsSuit | null;
  hearts_broken: boolean;
  trick_number: number;
  current_player_id: string | null;
  raw_scores: Record<string, number>;
  winner: string | null;
}

export interface WSHeartsPassingState extends WSHeartsStateBase {
  phase: "passing";
  hand_points: null;
  last_event: null;
}

export interface WSHeartsTrickState extends WSHeartsStateBase {
  phase: "trick";
  hand_points: null;
  last_event: null;
}

export interface WSHeartsRevealState extends WSHeartsStateBase {
  phase: "reveal";
  hand_points: null;
  last_event: HeartsLastEvent;
}

export interface WSHeartsHandOverState extends WSHeartsStateBase {
  phase: "hand_over";
  hand_points: Record<string, number>;
  last_event: HeartsLastEvent;
}

// ---- Werewolf: N players, secretly assigned roles, alternating night
// (hidden role actions) and day (open lynch vote) phases. Each night or
// day is ONE round - a simultaneous-but-role-scoped action set (only
// living werewolves + the living doctor + the living seer owe a night
// submission; everyone living owes a day vote). See werewolf_engine.py. ----

export type WerewolfRole = "werewolf" | "doctor" | "seer" | "villager";
export type WerewolfWinner = "werewolves" | "villagers";

export interface WerewolfLastEvent {
  kind: "night_result" | "day_result";
  night_number?: number;
  died_member_id?: string | null;
  lynched_member_id?: string | null;
  votes?: Record<string, string>;
}

interface WSWerewolfStateBase extends WSPartyStateBase {
  kind: "werewolf";
  night_number: number;
  my_role: WerewolfRole | null;
  alive: Record<string, boolean>;
  werewolf_team: string[] | null;
  my_seer_knowledge: Record<string, WerewolfRole> | null;
  all_roles: Record<string, WerewolfRole> | null;
  need_action: boolean;
  winner: WerewolfWinner | null;
}

export interface WSWerewolfNightState extends WSWerewolfStateBase {
  phase: "night_actions";
  last_event: null;
}

export interface WSWerewolfDayState extends WSWerewolfStateBase {
  phase: "day_vote";
  last_event: null;
}

export interface WSWerewolfRevealState extends WSWerewolfStateBase {
  phase: "reveal";
  last_event: WerewolfLastEvent;
}

// ---- Spades: strictly 4 players in fixed partnerships (seats 0&2 vs
// 1&3). Two round shapes interleaved within one hand, directly
// extending hearts_engine.py's pattern: a simultaneous "bidding" round
// (all 4 submit independently) and a single-actor "trick" round, with
// spades always trump. See spades_engine.py. ----

export type SpadesTeam = "team_a" | "team_b";

export interface SpadesCard {
  id: string;
  suit: HeartsSuit;
  rank: number;
}

export interface SpadesTrickEntry {
  member_id: string;
  card: SpadesCard;
}

export interface SpadesLastEvent {
  kind: "bids_in" | "card_played" | "trick_won";
  bids?: Record<string, number>;
  member_id?: string;
  card?: SpadesCard;
  cards?: SpadesCard[];
}

export interface SpadesHandResult {
  combined_bid: number;
  tricks_taken: number;
  hand_score: number;
  bag_penalty: number;
  cumulative_score: number;
}

interface WSSpadesStateBase extends WSPartyStateBase {
  kind: "spades";
  hand_number: number;
  teams: Record<SpadesTeam, string[]> | null;
  my_team: SpadesTeam | null;
  my_hand: SpadesCard[] | null;
  hand_sizes: Record<string, number>;
  my_bid: number | null;
  bids_submitted: string[];
  bids: Record<string, number> | null;
  current_trick: SpadesTrickEntry[];
  lead_suit: HeartsSuit | null;
  spades_broken: boolean;
  trick_number: number;
  current_player_id: string | null;
  team_scores: Record<SpadesTeam, number>;
  team_bags: Record<SpadesTeam, number>;
  winner: SpadesTeam | null;
}

export interface WSSpadesBiddingState extends WSSpadesStateBase {
  phase: "bidding";
  hand_results: null;
  last_event: null;
}

export interface WSSpadesTrickState extends WSSpadesStateBase {
  phase: "trick";
  hand_results: null;
  last_event: null;
}

export interface WSSpadesRevealState extends WSSpadesStateBase {
  phase: "reveal";
  hand_results: null;
  last_event: SpadesLastEvent;
}

export interface WSSpadesHandOverState extends WSSpadesStateBase {
  phase: "hand_over";
  hand_results: Record<SpadesTeam, SpadesHandResult>;
  last_event: SpadesLastEvent;
}

// ---- Buzzer Race: first valid action wins, not "everyone acts"
// (Trivia) or "one designated actor acts" (Uno) - a "buzzing" round
// accepts the FIRST buzz from any not-locked-out participant and
// rejects every submission after it; a wrong (or un-answered) buzz
// locks that player out of the current question and reopens buzzing
// for whoever's left. See buzzer_engine.py. ----

export interface BuzzerLastEvent {
  kind: "buzzed" | "correct" | "wrong" | "unsolved";
  member_id?: string;
  choice_index?: number;
  correct_index?: number | null;
}

interface WSBuzzerStateBase extends WSPartyStateBase {
  kind: "buzzer";
  question_number: number;
  num_questions: number;
  locked_out: string[];
  buzzed_member_id: string | null;
}

export interface WSBuzzerBuzzingState extends WSBuzzerStateBase {
  phase: "buzzing";
  question: TriviaQuestionPublic;
  last_event: null;
}

export interface WSBuzzerAnsweringState extends WSBuzzerStateBase {
  phase: "answering";
  question: TriviaQuestionPublic;
  last_event: null;
}

export interface WSBuzzerRevealState extends WSBuzzerStateBase {
  phase: "reveal";
  // Only revealed (carries correct_index) once the question is truly
  // settled (a correct answer, or everyone locked out) - still redacted
  // right after a bare "buzzed" or a "wrong" event, since the question
  // may still be live for the next buzzer. Check at runtime the same
  // way Trivia's own reveal view already does ("correct_index" in question).
  question: TriviaQuestionPublic | TriviaQuestionRevealed;
  last_event: BuzzerLastEvent;
}

// ---- Drawing & Guess: one player draws each turn on a shared canvas.
// The pen strokes themselves are NOT part of this party-state union at
// all - they're relayed live via the standalone WSDrawStroke/WSDrawClear
// events below (see realtime.py's draw_stroke/draw_clear handlers for
// why: a continuous pointer-coordinate stream has nothing in common
// with a discrete per-round action). This union only covers the
// turn-based game shell around that canvas. ----

export interface DrawingGuessEntry {
  member_id: string;
  text: string;
  correct: boolean;
}

export interface DrawingLastEvent {
  kind: "turn_over";
  drawer_member_id: string;
  word: string;
  correct_guesser_ids: string[];
}

interface WSDrawingStateBase extends WSPartyStateBase {
  kind: "drawing";
  turn_number: number;
  total_turns: number;
  current_drawer_id: string | null;
  am_drawer: boolean;
  word: string | null;
  word_length: number | null;
  round_started_at_ms: number | null;
  round_deadline_ms: number | null;
  guess_log: DrawingGuessEntry[];
  have_guessed_correctly: boolean;
  correct_guesser_ids: string[];
}

export interface WSDrawingDrawingState extends WSDrawingStateBase {
  phase: "drawing";
  last_event: null;
}

export interface WSDrawingRevealState extends WSDrawingStateBase {
  phase: "reveal";
  last_event: DrawingLastEvent;
}

export type WSPartyState =
  | WSPartyLobbyState
  | WSTriviaQuestionState
  | WSTriviaRevealState
  | WSDraftPickingState
  | WSDraftRevealState
  | WSDraftScoringRoundOverState
  | WSUnoTurnState
  | WSUnoRevealState
  | WSUnoHandOverState
  | WSCodenamesClueState
  | WSCodenamesGuessingState
  | WSCodenamesRevealState
  | WSHeartsPassingState
  | WSHeartsTrickState
  | WSHeartsRevealState
  | WSHeartsHandOverState
  | WSWerewolfNightState
  | WSWerewolfDayState
  | WSWerewolfRevealState
  | WSSpadesBiddingState
  | WSSpadesTrickState
  | WSSpadesRevealState
  | WSSpadesHandOverState
  | WSBuzzerBuzzingState
  | WSBuzzerAnsweringState
  | WSBuzzerRevealState
  | WSDrawingDrawingState
  | WSDrawingRevealState;

// Standalone stroke relay events (NOT part of WSPartyState - see the
// Drawing & Guess section above for why).
export interface DrawPoint {
  x: number;
  y: number;
}

export interface WSDrawStroke {
  type: "draw_stroke";
  party_game_id: string;
  stroke_id: string;
  points: DrawPoint[];
  color: string;
  width: number;
}

export interface WSDrawClear {
  type: "draw_clear";
  party_game_id: string;
}

export interface WSPartyCancelled {
  type: "party_cancelled";
  party_game_id: string;
}

// ---- Card games: poker is the first. A seated table of N players whose
// chip stacks persist across many hands in one sitting - a third,
// genuinely different shape from both the 2-seat board games and the
// round-based party games (see the backend's app/card_engines/base.py).
// One live card game per room at a time. ----

export type CardGameKind = "poker";
export type CardGameStatus = "lobby" | "active" | "finished" | "cancelled";
export type PokerPhase = "lobby" | "preflop" | "flop" | "turn" | "river" | "showdown" | "hand_over";
export type PokerActionKind = "fold" | "check" | "call" | "raise";

export interface PokerSeat {
  member_id: string;
  name: string;
  chips: number;
  bet_this_street: number;
  folded: boolean;
  all_in: boolean;
  sitting_out: boolean;
  // Present only for the viewer's own seat (pre-resolution) or for any
  // seat that reached showdown (post-resolution) - never for a folded
  // seat, even after the hand is over.
  hole_cards: [string, string] | null;
  hand_description: string | null;
}

export interface PokerLegalActions {
  actions: PokerActionKind[];
  call_amount: number;
  min_raise_to: number | null;
  max_raise_to: number | null;
}

export interface PokerPotSummary {
  amount: number;
  winners: string[];
  eligible: string[];
}

interface WSCardStateBase {
  type: "card_state";
  card_game_id: string;
  kind: CardGameKind;
  status: CardGameStatus;
  host_member_id: string;
  participant_ids: string[];
  starting_chips: number;
}

export interface WSCardLobbyState extends WSCardStateBase {
  phase: "lobby";
  seats: { member_id: string; name: string }[];
}

export interface WSCardActiveState extends WSCardStateBase {
  phase: Exclude<PokerPhase, "lobby">;
  hand_number: number;
  dealer_index: number;
  small_blind: number;
  big_blind: number;
  community_cards: string[];
  pot: number;
  current_bet: number;
  action_on: string | null;
  seats: PokerSeat[];
  my_legal_actions: PokerLegalActions;
  pot_summary: PokerPotSummary[] | null;
}

export type WSCardState = WSCardLobbyState | WSCardActiveState;

export interface WSCardCancelled {
  type: "card_cancelled";
  card_game_id: string;
}

export type WSServerEvent =
  | WSReady
  | WSMessage
  | WSMessageDeleted
  | WSPins
  | WSReaction
  | WSPresence
  | WSMemberJoined
  | WSMemberLeft
  | WSRoleChanged
  | WSOwnershipOffer
  | WSOwnershipChanged
  | WSChannelCreated
  | WSRemoved
  | WSRoomDeleted
  | WSRoomEnded
  | WSError
  | WSMusicStarted
  | WSMusicStopped
  | WSMusicQueueUpdated
  | WSMusicRequested
  | WSCallPresence
  | WSCallInvite
  | WSCallOffer
  | WSCallAnswer
  | WSIceCandidate
  | WSPhotoShared
  | WSGameInvite
  | WSGameDeclined
  | WSGameCancelled
  | WSGameState
  | WSGameLive
  | WSGameLiveEnded
  | WSGameWatchers
  | WSGameLinkWaiting
  | WSPartyState
  | WSPartyCancelled
  | WSDrawStroke
  | WSDrawClear
  | WSCardState
  | WSCardCancelled;

export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
  }
}
