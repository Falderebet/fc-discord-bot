import os
import random
import discord
import sqlite3
from discord.ext import commands

# Connect to SQLite database (this will create the file if it doesn't exist)
conn = sqlite3.connect('elo_ratings.db')
c = conn.cursor()

# Create table for players
c.execute('''
CREATE TABLE IF NOT EXISTS players (
    player_id INTEGER PRIMARY KEY,
    display_name TEXT,
    elo INTEGER
)
''')

# Create table for games
c.execute('''
CREATE TABLE IF NOT EXISTS games (
    game_id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    state TEXT,
    team1_score INTEGER,
    team2_score INTEGER,
    team1 TEXT,
    team2 TEXT
)
''')

conn.commit()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# This will store the game information
games = {}

# Database to store players' Elo ratings
players_elo = {}

# Constants for Elo calculation
K_FACTOR = 128
BASE_ELO = 1000

TOKEN = ""

# Function to calculate Elo change
def calculate_elo_change(team_elo_avg, opponent_elo_avg, result):
    expected_score = 1 / (1 + 10 ** ((opponent_elo_avg - team_elo_avg) / 400))
    return round(K_FACTOR * (result - expected_score))

# Function to update Elo ratings
async def update_elo(ctx, current_team, opponent_ids, result):

    # Fetch all the current teams players Elo or assign BASE_ELO if they are not found
    current_team_elos = []
    for player_id in current_team:
        c.execute('SELECT elo FROM players WHERE player_id = ?', (player_id,))
        player = c.fetchone()
        if player:
            current_team_elos.append(player[0])
        else:
            current_team_elos.append(BASE_ELO)
            c.execute('INSERT INTO players (player_id, elo, display_name) VALUES (?, ?, ?)', (player_id, BASE_ELO, players_elo[player_id]['display_name']))
    
    
    c.execute('SELECT elo FROM players WHERE player_id = ?', (player_id,))
    player = c.fetchone()
    if player:
        player_elo = player[0]
    else:
        player_elo = BASE_ELO
        c.execute('INSERT INTO players (player_id, elo, display_name) VALUES (?, ?, ?)', (player_id, BASE_ELO, players_elo[player_id]['display_name']))
        
    # Calculate average Elo of opponents
    opponent_elos = []
    for opp_id in opponent_ids:
        c.execute('SELECT elo FROM players WHERE player_id = ?', (opp_id,))
        opp = c.fetchone()
        if opp:
            opponent_elos.append(opp[0])
        else:
            opponent_elos.append(BASE_ELO)
            c.execute('INSERT INTO players (player_id, elo, display_name) VALUES (?, ?, ?)', (opp_id, BASE_ELO, players_elo[opp_id]['display_name']))
    
    opponent_elo_avg = sum(opponent_elos) / len(opponent_ids)
    
    current_team_elo_avg = sum(current_team_elos) / len(current_team)
    
    
    # Calculate Elo change and update
    elo_change = calculate_elo_change(current_team_elo_avg, opponent_elo_avg, result)
    
    for player_id, player_elo in zip(current_team, current_team_elos):
        new_elo = player_elo + elo_change
        if new_elo < 100:
            new_elo = 100
            
        c.execute('UPDATE players SET elo = ? WHERE player_id = ?', (new_elo, player_id))
        conn.commit()
        
        # get the display name of the player
        c.execute('SELECT display_name FROM players WHERE player_id = ?', (player_id,))
        display_name = c.fetchone()[0]
        
        await ctx.send(f'Updated Elo for {display_name}: {player_elo} -> {new_elo} ({elo_change:+})')
    

@bot.command(name='getPlayers')
async def getPlayers(ctx):
    # Fetch all members from all guilds
    for guild in bot.guilds:
        print(f'Adding {guild.name} to the database')
        for member in guild.members:
            # Check if the member is a bot
            if member.bot:
                continue

            print(f'Adding {member.display_name} to the database')
            print(f'Adding {member.id} to the database')
            
            # Insert member into the database if they are not already present
            c.execute('SELECT * FROM players WHERE player_id = ?', (member.id,))
            if c.fetchone() is None:
                c.execute('INSERT INTO players (player_id, elo, display_name) VALUES (?, ?, ?)', (member.id, BASE_ELO, member.display_name))
    
    conn.commit()
    print("All members have been added to the database")


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.display_name}')

    # Fetch all members from all guilds
    for guild in bot.guilds:
        for member in guild.members:
            # Check if the member is a bot
            if member.bot:
                continue

            print(f'Adding {member.display_name} to the database')
            print(f'Adding {member.id} to the database')
            
            # Insert member into the database if they are not already present
            c.execute('SELECT * FROM players WHERE player_id = ?', (member.id,))
            if c.fetchone() is None:
                c.execute('INSERT INTO players (player_id, elo, display_name) VALUES (?, ?, ?)', (member.id, BASE_ELO, member.display_name))
    
    conn.commit()
    print("All members have been added to the database")

@bot.command(name='play')
async def play(ctx):
    if ctx.guild.id not in games:
        games[ctx.guild.id] = {'players': [], 'state': 'waiting', 'result': None, 'votes': {}}
    
    game = games[ctx.guild.id]

    if ctx.author in game['players']:
        await ctx.send("You're already in the game!") 
        return

    if game['state'] != 'waiting':
        await ctx.send("A game is already in progress.")
        return

    game['players'].append(ctx.author)
    await ctx.send(f'{ctx.author.display_name} has joined the game! ({len(game["players"])}/4)')

    if len(game['players']) == 4:
        players = game['players']
        random.shuffle(players)
        team1 = players[:2]
        team2 = players[2:]
        game['team1'] = team1
        game['team2'] = team2
        game['state'] = 'started'
        team1_tot_elo = c.execute('SELECT SUM(elo) FROM players WHERE player_id IN (?, ?)', (team1[0].id, team1[1].id)).fetchone()[0]
        team2_tot_elo = c.execute('SELECT SUM(elo) FROM players WHERE player_id IN (?, ?)', (team2[0].id, team2[1].id)).fetchone()[0]
        await ctx.send(f'The teams are:\nTeam 1: **{team1[0].display_name}**, **{team1[1].display_name}** - tot: {team1_tot_elo/2}\nTeam 2: **{team2[0].display_name}**, **{team2[1].display_name}** - tot: {team2_tot_elo/2} \n\nPlease report the result using:\n !result {{team1 total wins}} {{team2 total wins}}')
    
    # Initialize Elo rating for new player
    c.execute('SELECT * FROM players WHERE player_id = ?', (ctx.author.id,))
    if c.fetchone() is None:
        # Player does not exist, so insert them
        c.execute('INSERT INTO players (player_id, elo, display_name) VALUES (?, ?, ?)', (ctx.author.id, BASE_ELO, ctx.author.display_name))
        conn.commit()
    

@bot.command(name='result')
async def result(ctx, *results: str):
    game = games.get(ctx.guild.id)

    if not game or game['state'] != 'started':
        await ctx.send("No game is currently in progress.")
        return

    if ctx.author not in game['team1'] + game['team2']:
        await ctx.send("You are not part of the current game.")
        return

    team1_wins = 0
    team2_wins = 0
    for result in results:
        team1_score, team2_score = map(int, result.split('-'))
        if team1_score > team2_score:
            team1_wins += 1
        else:
            team2_wins += 1

    game['result'] = {'team1_wins': team1_wins, 'team2_wins': team2_wins, 'reporter': ctx.author}
    game['votes'] = {player: None for player in game['team1'] + game['team2']}
    game['votes'][ctx.author] = 'yes'
    
    result_str = ' '.join(results)
    await ctx.send(f'Result reported by {ctx.author.display_name}: {result_str}\n\n !vote yes to confirm results.')

@bot.command(name='vote')
async def vote(ctx, vote: str):
    game = games.get(ctx.guild.id)

    if not game or game['state'] != 'started' or not game['result']:
        await ctx.send("No game result is awaiting votes.")
        return

    if ctx.author not in game['votes']:
        await ctx.send("You are not part of the current game.")
        return

    if game['votes'][ctx.author] is not None:
        await ctx.send("You have already voted.")
        return

    if vote.lower() not in ['yes', 'no']:
        await ctx.send("Vote must be 'yes' or 'no'.")
        return

    game['votes'][ctx.author] = vote.lower()
    await ctx.send(f'{ctx.author.display_name} voted {vote}.')

    if 'no' in game['votes'].values():
        await ctx.send("The result has been rejected. Please report the correct result.")
        game['result'] = None
        game['votes'] = {}
        return

    if all(vote == 'yes' for vote in game['votes'].values() if vote is not None):
        await ctx.send("The result has been accepted.")
        
        # Calculate Elo change and update Elo ratings
        team1_ids = [player.id for player in game['team1']]
        team2_ids = [player.id for player in game['team2']]
        team1_wins = game['result']['team1_wins']
        team2_wins = game['result']['team2_wins']
        total_games = team1_wins + team2_wins
        result_team1 = team1_wins / total_games if total_games > 0 else 0.5
        result_team2 = team2_wins / total_games if total_games > 0 else 0.5
        await update_elo(ctx, team1_ids, team2_ids, result_team1)
        await update_elo(ctx, team2_ids, team1_ids, result_team2)

        # Save the game to the games table
        c.execute('INSERT INTO games (guild_id, state, team1_score, team2_score, team1, team2) VALUES (?, ?, ?, ?, ?, ?)', (ctx.guild.id, 'completed', team1_wins, team2_wins, str(team1_ids), str(team2_ids)))
            
        game['state'] = 'waiting'
        game['players'] = []
        game['result'] = None
        game['votes'] = {}
        
@bot.command(name="ranking")
async def ranking(ctx):
    c.execute('SELECT display_name, elo FROM players ORDER BY elo DESC')
    players = c.fetchall()

    if not players:
        await ctx.send("No Elo ratings available.")
        return

    # Create the ranking message
    ranking_message = ""
    for i, player in enumerate(players, start=1):
        ranking_message += f"{i}. {player[0]}: {player[1]}\n"

    await ctx.send(f'**Elo Rankings:**\n{ranking_message}')

@bot.command(name='editElo')
async def edit_elo(ctx, player_id: int, new_elo: int):
    if ctx.author.id != 186150770163318784:
        await ctx.send("You do not have permission to edit Elo ratings.")
        return
    
    c.execute('UPDATE players SET elo = ? WHERE player_id = ?', (new_elo, player_id))
    conn.commit()
    await ctx.send(f'Elo for player {player_id} has been updated to {new_elo}.')
    

@bot.command(name='cancel')
async def cancel(ctx):
    games[ctx.guild.id] = {'players': [], 'state': 'waiting', 'result': None, 'votes': {}}

    await ctx.send("Game has been cancelled and has not been saved.")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument): 
        await ctx.send(f"Error: Missing required argument `{error.param.name}`. Please provide all required arguments.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Error: Invalid argument type.\n - **!play** to start playing 💩\n - **!cancel** to reset current game 🙆")
    else:
        await ctx.send("An error occurred while processing the command.\n- **!play** to start playing 💩\n- **!cancel** to reset current game 🙆")
    raise error  # Re-raise the error so it's still logged

bot.run(TOKEN)
