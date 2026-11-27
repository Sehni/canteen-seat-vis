import streamlit as st
import matplotlib.pyplot as plt
from PIL import Image
import numpy as np
import os
import time
import io

# ==========================================
# 1. 数据解析
# ==========================================
@st.cache_data
def parse_data(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    right_lines, left_blocks, current_block, current_time = [], [], [], ""
    
    for line in lines:
        line = line.strip()
        if not line or "特定区域" in line:
            continue
        
        if ':' in line:
            if current_block:
                left_blocks.append((current_time, current_block))
                current_block = []
            current_time = line
        else:
            if current_time:
                current_block.append(line)
            else:
                right_lines.append(line)
                
    if current_block:
        left_blocks.append((current_time, current_block))
        
    def extract_nums(line_list):
        result = []
        for line in line_list:
            for part in line.split():
                result.extend([int(c) for c in part])
        return result

    right_data = [extract_nums([line]) for line in right_lines]
    left_data, times = [], []
    
    for time_label, block in left_blocks:
        times.append(time_label)
        for line in block:
            left_data.append(extract_nums([line]))
            
    time_steps = []
    for t in range(5):
        time_steps.append({
            'time_label': times[t] if t < len(times) else f"T+{t*5}",
            'right_1': right_data[t*2] if t*2 < len(right_data) else [0]*36,
            'right_2': right_data[t*2+1] if t*2+1 < len(right_data) else [0]*36,
            'left_1':  left_data[t*2] if t*2 < len(left_data) else [0]*36,
            'left_2':  left_data[t*2+1] if t*2+1 < len(left_data) else [0]*36
        })
    return time_steps

# ==========================================
# 2. 图像渲染类 (保持不变)
# ==========================================
class Unit:
    def __init__(self, x, y, assets, ax):
        self.x, self.y = x, y
        self.ax = ax
        self.assets = assets
        self.desk_w = 2.2      
        self.seat_w = 0.8      
        self.load_desk()
        self.load_seat()
        
    def load_desk(self):
        extent = (self.x - self.desk_w/2, self.x + self.desk_w/2, 
                  self.y - self.desk_w/2, self.y + self.desk_w/2)
        self.desk = self.ax.imshow(self.assets['desk'], extent=extent, zorder=0, aspect='auto')
        
    def load_seat(self):
        self.seat = []
        offset = self.desk_w / 4.0  
        directions = [(-1, 1), (-1, -1), (1, -1), (1, 1)] 
        
        for dx, dy in directions:
            sx = self.x + dx * offset
            sy = self.y + dy * offset
            extent = (sx - self.seat_w/2, sx + self.seat_w/2, 
                      sy - self.seat_w/2, sy + self.seat_w/2)
            
            blank = self.ax.imshow(self.assets['blank'], extent=extent, zorder=10, aspect='auto')
            person = self.ax.imshow(self.assets['person'], extent=extent, zorder=10, aspect='auto')
            stuff = self.ax.imshow(self.assets['stuff'], extent=extent, zorder=10, aspect='auto')
            
            self.seat.append((blank, person, stuff))
            blank.set_visible(False)
            person.set_visible(False)
            stuff.set_visible(False)

    def shift(self, place, state):
        for i in range(3):
            self.seat[place][i].set_visible(i == state)

class Editor:
    def __init__(self, assets):
        self.fig, self.ax = plt.subplots(figsize=(15, 5), dpi=100)
        self.fig.patch.set_alpha(0.0)
        self.ax.patch.set_alpha(0.0)
        
        self.ax.set_xlim(-32, 32)
        self.ax.set_ylim(-3, 11)
        self.ax.set_aspect('equal')
        self.ax.axis('off')
        
        self.assets = assets
        self.ax.fill_between([-31, -5], -2.5, 10.5, color='#f0f2f6', zorder=-5)
        self.ax.fill_between([5, 31], -2.5, 10.5, color='#f0f2f6', zorder=-5)

        self.units = {'left_1': [], 'left_2': [], 'right_1': [], 'right_2': []}
        self.create_layout()

    def create_layout(self):
        x_left = np.linspace(-28, -8, 9) 
        x_right = np.linspace(8, 28, 9)  
        
        for x in x_left[::-1]: 
            self.units['left_1'].append(Unit(x=x, y=1, assets=self.assets, ax=self.ax))
        for x in x_left: 
            self.units['left_2'].append(Unit(x=x, y=7, assets=self.assets, ax=self.ax))
            
        for x in x_right: 
            self.units['right_1'].append(Unit(x=x, y=1, assets=self.assets, ax=self.ax))
        for x in x_right[::-1]: 
            self.units['right_2'].append(Unit(x=x, y=7, assets=self.assets, ax=self.ax))

    def update_state(self, step_data):
        mapping = {
            'left_1':  step_data['left_1'], 
            'left_2':  step_data['left_2'], 
            'right_1': step_data['right_1'], 
            'right_2': step_data['right_2']
        }
        for key, data_array in mapping.items():
            units_list = self.units[key]
            for i, unit in enumerate(units_list):
                seat_states = data_array[i*4 : (i+1)*4]
                for seat_idx in range(4):
                    unit.shift(seat_idx, seat_states[seat_idx])

# ==========================================
# 3. 缓存图片加载
# ==========================================
@st.cache_resource
def load_images():
    def load_image(path):
        try:
            with Image.open(path) as im:
                im = im.convert("RGBA")
                im.thumbnail((128, 128), Image.Resampling.LANCZOS) 
                return np.asarray(im, dtype=np.float32) / 255.0
        except FileNotFoundError:
            color = [0.9, 0.2, 0.2, 1] if "有人" in path else ([0.9, 0.8, 0.2, 1] if "占座" in path else [0.8, 0.8, 0.8, 1])
            return np.ones((64, 64, 4), dtype=np.float32) * color

    return {
        'desk': load_image("assets/空座位.png"), 
        'blank': load_image("assets/空座位.png"),
        'stuff': load_image("assets/占座.png"),
        'person': load_image("assets/有人.png")
    }

# 单帧渲染函数，带有缓存
@st.cache_data(show_spinner=False)
def render_single_frame(time_idx, step_data):
    assets = load_images()
    editor = Editor(assets)
    editor.update_state(step_data)
    
    buf = io.BytesIO()
    editor.fig.savefig(buf, format="png", transparent=True, bbox_inches='tight', pad_inches=0.1, dpi=120)
    plt.close(editor.fig) # 及时释放内存
    buf.seek(0)
    return buf.getvalue()

# ==========================================
# 4. Streamlit 主程序
# ==========================================
def main():
    st.set_page_config(page_title="食堂座位状态监控", layout="wide")
    st.title("🍽️ 食堂座位状态监控")
    
    file_path = os.path.join("data", "data1-11.25.txt")
    try:
        time_steps = parse_data(file_path)
    except Exception as e:
        st.error(f"数据读取失败：{e}。")
        return

    if 'time_idx' not in st.session_state:
        st.session_state.time_idx = 0
    if 'is_playing' not in st.session_state:
        st.session_state.is_playing = False

    # ==========================================
    # 🌟 核心：启动时集中渲染所有图片并展示进度条
    # ==========================================
    if 'all_images' not in st.session_state:
        st.info("正在初始化渲染引擎，请稍候...")
        progress_bar = st.progress(0, text="正在生成图像...")
        
        images_cache = []
        for i, step in enumerate(time_steps):
            # 调用缓存的单帧渲染（第一次运行会真正画图，之后哪怕重启程序也是秒读缓存）
            img_bytes = render_single_frame(i, step)
            images_cache.append(img_bytes)
            progress_bar.progress((i + 1) / len(time_steps), text=f"正在生成第 {i+1}/{len(time_steps)} 帧...")
            
        st.session_state.all_images = images_cache
        progress_bar.empty()  # 加载完毕后移除进度条
        st.rerun()  # 刷新界面进入主程序

    # ==========================================
    # 自动播放引擎
    # ==========================================
    if st.session_state.is_playing:
        if st.session_state.time_idx < len(time_steps) - 1:
            time.sleep(1.0) 
            st.session_state.time_idx += 1
            st.rerun()
        else:
            st.session_state.is_playing = False
            st.rerun()

    def pause_playback():
        st.session_state.is_playing = False

    # ==========================================
    # 侧边栏 UI
    # ==========================================
    st.sidebar.header("控制面板")
    
    play_btn_text = "⏸️ 暂停播放" if st.session_state.is_playing else "▶️ 开始播放"
    st.sidebar.button(play_btn_text, on_click=lambda: st.session_state.update(is_playing=not st.session_state.is_playing), use_container_width=True)
    
    st.sidebar.slider(
        "拖动查看时间点", 
        min_value=0, 
        max_value=len(time_steps)-1, 
        key="time_idx",          
        on_change=pause_playback 
    )
        
    current_step = time_steps[st.session_state.time_idx]
    st.sidebar.info(f"当前时间：**{current_step['time_label']}**")
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 图例说明")
    st.sidebar.markdown("- ⚪ 空位：0（空）")
    st.sidebar.markdown("- 🔴 有人：1（有人）")
    st.sidebar.markdown("- 🟡 物品：2（有物品）")

    # ==========================================
    # 🌟 直接展示内存里的图片，彻底告别绘图耗时
    # ==========================================
    st.image(st.session_state.all_images[st.session_state.time_idx], use_container_width=True)

if __name__ == "__main__":
    main()
