from flask import Flask, render_template, request, redirect, url_for, jsonify
import json
import os
import time
import requests
import threading

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'

ANIME_FILE = 'anime.json'

def load_anime():
    if os.path.exists(ANIME_FILE):
        try:
            with open(ANIME_FILE, 'r', encoding='utf-8') as file:
                data = file.read().strip()
                anime_list = json.loads(data) if data else []
                for anime in anime_list:
                    for season in anime.get('seasons', []):
                        for video in season.get('videos', []):
                            if 'link' in video and isinstance(video['link'], str):
                                video['links'] = {'720p': video['link']}
                                del video['link']
                return anime_list
        except json.JSONDecodeError:
            return []
    return []

def save_anime(anime_list):
    with open(ANIME_FILE, 'w', encoding='utf-8') as file:
        json.dump(anime_list, file, indent=4, ensure_ascii=False)

def generate_anime_id(anime_list):
    if not anime_list:
        return 1
    return max(anime['id'] for anime in anime_list) + 1

def generate_video_id(anime_list):
    max_id = 0
    for anime in anime_list:
        for season in anime['seasons']:
            for video in season['videos']:
                if video['id'] > max_id:
                    max_id = video['id']
    return max_id + 1

@app.route('/')
def home():
    page = request.args.get('page', 1, type=int)
    per_page = 8
    search_query = request.args.get('search', '')
    
    anime_list = load_anime()
    anime_list.sort(key=lambda x: x['id'], reverse=True)
    
    if search_query:
        search_lower = search_query.lower()
        filtered_anime = []
        for anime in anime_list:
            if search_lower in anime['name'].lower():
                filtered_anime.append(anime)
                continue
            for season in anime['seasons']:
                for video in season['videos']:
                    if (search_lower in video['title'].lower() or 
                        search_lower in video['description'].lower()):
                        filtered_anime.append(anime)
                        break
        anime_list = list({a['id']:a for a in filtered_anime}.values())
    
    total_pages = (len(anime_list) + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    paginated_anime = anime_list[start_idx:start_idx+per_page]
    
    return render_template('index.html',
                         anime_list=paginated_anime,
                         page=page,
                         total_pages=total_pages,
                         search_query=search_query)

@app.route('/anime/<int:anime_id>')
def anime_details(anime_id):
    anime_list = load_anime()
    anime = next((a for a in anime_list if a['id'] == anime_id), None)
    
    if not anime:
        return "Anime not found", 404
    
    min_season = min(s['season_number'] for s in anime['seasons'])
    selected_season = request.args.get('season', min_season)
    season = next((s for s in anime['seasons'] if str(s['season_number']) == str(selected_season)), None)
    
    if not season:
        return "Season not found", 404
    
    season['videos'].sort(key=lambda x: x['serial'])
    
    return render_template('anime.html',
                         anime=anime,
                         season=season,
                         seasons=anime['seasons'])

@app.route('/video/<int:video_id>')
def video_player(video_id):
    anime_list = load_anime()
    for anime in anime_list:
        for season in anime['seasons']:
            for video in season['videos']:
                if video['id'] == video_id:
                    sorted_videos = sorted(season['videos'], key=lambda x: x['serial'])
                    current_index = next(i for i, v in enumerate(sorted_videos) if v['id'] == video_id)
                    
                    next_episodes = sorted_videos[current_index+1:current_index+6]
                    prev_episodes = sorted_videos[max(0, current_index-2):current_index][::-1]
                    
                    for ep in next_episodes:
                        ep['short_description'] = ep['description'][:100] + '...' if len(ep['description']) > 100 else ep['description']
                    for ep in prev_episodes:
                        ep['short_description'] = ep['description'][:100] + '...' if len(ep['description']) > 100 else ep['description']
                    
                    available_qualities = list(video['links'].keys())
                    default_quality = None
                    for q in ['720p', '1080p', '480p']:
                        if q in available_qualities:
                            default_quality = q
                            break
                    if not default_quality and available_qualities:
                        default_quality = available_qualities[0]
                    
                    return render_template('video.html',
                                         video=video,
                                         anime_name=anime['name'],
                                         next_episodes=next_episodes,
                                         prev_episodes=prev_episodes,
                                         default_quality=default_quality)
    return "Video not found", 404

@app.route('/add_anime', methods=['GET', 'POST'])
def add_anime():
    if request.method == 'POST':
        anime_name = request.form['anime_name']
        anime_image = request.form['anime_image']
        anime_description = request.form['anime_description']
        season_number = request.form['season_number']

        anime_list = load_anime()
        if any(a['name'].lower() == anime_name.lower() for a in anime_list):
            return "Anime already exists!", 400

        new_anime = {
            'id': generate_anime_id(anime_list),
            'name': anime_name,
            'image': anime_image,
            'description': anime_description,
            'seasons': [{
                'season_number': int(season_number),
                'videos': []
            }]
        }

        anime_list.append(new_anime)
        save_anime(anime_list)
        return redirect(url_for('video_admin'))

    return render_template('add_anime.html')

@app.route('/ad_video', methods=['GET', 'POST'])
def video_admin():
    anime_list = load_anime()
    
    if request.method == 'POST':
        if 'step' in request.form:
            if request.form['step'] == 'select':
                anime_id = int(request.form['anime_id'])
                season_number = int(request.form['season_number'])
                return redirect(url_for('video_admin', anime_id=anime_id, season_number=season_number))
            
            elif request.form['step'] == 'add':
                anime_id = int(request.form['anime_id'])
                season_number = int(request.form['season_number'])
                video_title = request.form['video_title']
                video_link_1080 = request.form.get('video_link_1080')
                video_link_720 = request.form.get('video_link_720', '')
                video_link_480 = request.form.get('video_link_480')
                thumbnail_link = request.form['thumbnail_link']
                video_description = request.form['video_description']
                serial_number = request.form['serial_number']

                if not video_link_720:
                    return "720p link is required", 400

                links = {}
                if video_link_1080:
                    links['1080p'] = video_link_1080
                if video_link_720:
                    links['720p'] = video_link_720
                if video_link_480:
                    links['480p'] = video_link_480

                anime = next((a for a in anime_list if a['id'] == anime_id), None)
                if not anime:
                    return "Anime not found", 404

                season = next((s for s in anime['seasons'] if s['season_number'] == season_number), None)
                if not season:
                    season = {'season_number': season_number, 'videos': []}
                    anime['seasons'].append(season)

                video_id = generate_video_id(anime_list)
                season['videos'].append({
                    'id': video_id,
                    'title': video_title,
                    'links': links,
                    'thumbnail': thumbnail_link,
                    'description': video_description,
                    'serial': int(serial_number)
                })

                save_anime(anime_list)
                return redirect(url_for('video_admin'))

    anime_id = request.args.get('anime_id', type=int)
    season_number = request.args.get('season_number', type=int)
    selected_anime = next((a for a in anime_list if a['id'] == anime_id), None) if anime_id else None
    selected_season = next((s for s in selected_anime['seasons'] if s['season_number'] == season_number), None) if selected_anime else None

    return render_template('ad_video.html',
                         anime_list=anime_list,
                         selected_anime=selected_anime,
                         selected_season=selected_season)

@app.route('/edit_anime/<int:anime_id>', methods=['GET', 'POST'])
def edit_anime(anime_id):
    anime_list = load_anime()
    anime = next((a for a in anime_list if a['id'] == anime_id), None)
    if not anime:
        return "Anime not found", 404

    if request.method == 'POST':
        anime['name'] = request.form['name']
        anime['image'] = request.form['image']
        anime['description'] = request.form['description']
        save_anime(anime_list)
        return redirect(url_for('edit_anime_select'))

    return render_template('edit_anime.html', anime=anime)

@app.route('/ed_video/<int:video_id>', methods=['GET', 'POST'])
def edit_video(video_id):
    anime_list = load_anime()
    target_video = None
    old_anime = None
    old_season = None

    for anime in anime_list:
        for season in anime['seasons']:
            for video in season['videos']:
                if video['id'] == video_id:
                    target_video = video
                    old_anime = anime
                    old_season = season
                    break

    if not target_video:
        return "Video not found", 404

    if request.method == 'POST':
        new_season_number = int(request.form['season_number'])
        new_serial = int(request.form['serial_number'])
        video_title = request.form['video_title']
        video_link_1080 = request.form.get('video_link_1080')
        video_link_720 = request.form.get('video_link_720', '')
        video_link_480 = request.form.get('video_link_480')
        thumbnail_link = request.form['thumbnail_link']
        video_description = request.form['video_description']

        if not video_link_720:
            return "720p link is required", 400

        links = {}
        if video_link_1080:
            links['1080p'] = video_link_1080
        if video_link_720:
            links['720p'] = video_link_720
        if video_link_480:
            links['480p'] = video_link_480

        target_video.update({
            'title': video_title,
            'links': links,
            'thumbnail': thumbnail_link,
            'description': video_description,
            'serial': new_serial
        })

        if new_season_number != old_season['season_number']:
            old_season['videos'].remove(target_video)
            if not old_season['videos']:
                old_anime['seasons'].remove(old_season)

            new_season = next((s for s in old_anime['seasons'] if s['season_number'] == new_season_number), None)
            if not new_season:
                new_season = {'season_number': new_season_number, 'videos': []}
                old_anime['seasons'].append(new_season)
            new_season['videos'].append(target_video)

        save_anime(anime_list)
        return redirect(url_for('video_admin'))

    return render_template('ed_video.html',
                         video=target_video,
                         current_anime=old_anime,
                         current_season=old_season['season_number'])

@app.route('/delete_video/<int:video_id>')
def delete_video(video_id):
    anime_list = load_anime()
    for anime in anime_list[:]:
        for season in anime['seasons'][:]:
            season['videos'] = [v for v in season['videos'] if v['id'] != video_id]
            if not season['videos']:
                anime['seasons'].remove(season)
        if not anime['seasons']:
            anime_list.remove(anime)
    save_anime(anime_list)
    return redirect(url_for('video_admin'))

@app.route('/edit_dashboard')
def edit_dashboard():
    return render_template('edit_dashboard.html')

@app.route('/edit_video_select_anime')
def edit_video_select_anime():
    anime_list = load_anime()
    return render_template('edit_video_select_anime.html', anime_list=anime_list)

@app.route('/edit_video_select_season/<int:anime_id>')
def edit_video_select_season(anime_id):
    anime_list = load_anime()
    anime = next((a for a in anime_list if a['id'] == anime_id), None)
    if not anime:
        return "Anime not found", 404
    return render_template('edit_video_select_season.html', anime=anime)

@app.route('/edit_video_list/<int:anime_id>/<int:season_number>')
def edit_video_list(anime_id, season_number):
    anime_list = load_anime()
    anime = next((a for a in anime_list if a['id'] == anime_id), None)
    if not anime:
        return "Anime not found", 404
    season = next((s for s in anime['seasons'] if s['season_number'] == season_number), None)
    if not season:
        return "Season not found", 404
    videos = season['videos']
    return render_template('edit_video_list.html', anime=anime, season=season, videos=videos)

@app.route('/edit_anime_select')
def edit_anime_select():
    anime_list = load_anime()
    return render_template('edit_anime_select.html', anime_list=anime_list)

@app.route('/delete_anime/<int:anime_id>')
def delete_anime(anime_id):
    anime_list = load_anime()
    anime_list = [a for a in anime_list if a['id'] != anime_id]
    save_anime(anime_list)
    return redirect(url_for('edit_anime_select'))

@app.route('/add_season/<int:anime_id>', methods=['POST'])
def add_season(anime_id):
    anime_list = load_anime()
    anime = next((a for a in anime_list if a['id'] == anime_id), None)
    if not anime:
        return "Anime not found", 404
    season_number = request.form.get('season_number')
    if not season_number:
        return "Season number is required", 400
    try:
        season_number = int(season_number)
    except ValueError:
        return "Invalid season number", 400
    if any(s['season_number'] == season_number for s in anime['seasons']):
        return "Season number already exists", 400
    anime['seasons'].append({'season_number': season_number, 'videos': []})
    save_anime(anime_list)
    return redirect(url_for('edit_anime', anime_id=anime_id))

@app.route('/delete_season/<int:anime_id>/<int:season_number>')
def delete_season(anime_id, season_number):
    anime_list = load_anime()
    anime = next((a for a in anime_list if a['id'] == anime_id), None)
    if not anime:
        return "Anime not found", 404
    season = next((s for s in anime['seasons'] if s['season_number'] == season_number), None)
    if not season:
        return "Season not found", 404
    anime['seasons'].remove(season)
    if not anime['seasons']:
        anime_list.remove(anime)
    save_anime(anime_list)
    return redirect(url_for('edit_anime', anime_id=anime_id))

@app.route('/json')
def show_json():
    anime_list = load_anime()
    return jsonify(anime_list)
    
@app.errorhandler(404)
def page_not_found(error):
    return render_template('404.html'), 404

@app.route('/get_seasons/<int:anime_id>')
def get_seasons(anime_id):
    anime_list = load_anime()
    anime = next((a for a in anime_list if a['id'] == anime_id), None)
    if not anime:
        return jsonify({"error": "Anime not found"}), 404
    return jsonify({"seasons": anime['seasons']})

@app.route('/ad', methods=['GET'])
def add_video_via_get():
    # Extract parameters from query string
    anime_id = request.args.get('a', type=int)
    season_number = request.args.get('s', type=int)
    title = request.args.get('t')
    link_720p = request.args.get('720p')
    link_480p = request.args.get('480p')
    link_1080p = request.args.get('1080p')
    thumbnail = request.args.get('th')
    description = request.args.get('d')
    serial = request.args.get('eps', type=int)  # Assuming 'eps' is the serial parameter

    # Check for mandatory parameters
    mandatory_params = [anime_id, season_number, title, link_720p, thumbnail, description, serial]
    if None in mandatory_params:
        return jsonify({
            "status": "error",
            "message": "Missing mandatory parameters. Required: a, s, t, 720p, th, d, eps"
        }), 400

    # Load anime data
    anime_list = load_anime()
    
    # Find the target anime
    anime = next((a for a in anime_list if a['id'] == anime_id), None)
    if not anime:
        return jsonify({"status": "error", "message": "Anime not found"}), 404

    # Find or create the season
    season = next((s for s in anime['seasons'] if s['season_number'] == season_number), None)
    if not season:
        season = {'season_number': season_number, 'videos': []}
        anime['seasons'].append(season)

    # Create links dictionary
    links = {'720p': link_720p}
    if link_480p:
        links['480p'] = link_480p
    if link_1080p:
        links['1080p'] = link_1080p

    # Generate video ID
    video_id = generate_video_id(anime_list)

    # Create new video entry
    new_video = {
        'id': video_id,
        'title': title,
        'links': links,
        'thumbnail': thumbnail,
        'description': description,
        'serial': serial
    }

    # Add video to season
    season['videos'].append(new_video)
    save_anime(anime_list)

    # Return success response
    return jsonify({
        "status": "success",
        "message": "Video added successfully",
        "video": {
            "id": video_id,
            "title": title,
            "links": links,
            "thumbnail": thumbnail,
            "description": description,
            "serial": serial
        },
        "anime_id": anime_id,
        "season": season_number
    }), 200
    
@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "alive"})

def keep_alive():
    url = "https://nekofilx.onrender.com"
    while True:
        time.sleep(300)
        try:
            requests.get(url)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == '__main__':
    if not os.path.exists(ANIME_FILE):
        save_anime([])
    
    threading.Thread(target=keep_alive, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
