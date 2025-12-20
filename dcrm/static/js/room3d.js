class Room3DRenderer {
    constructor(config) {
        // 基础配置
        this.container = config.container;
        this.dataUrl = config.dataUrl;
        
        // Three.js 组件
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        
        // 数据存储
        this.roomData = null;
        this.rackObjects = new Map();
        
        // 添加拖拽控制器
        this.dragControls = null;
        this.selectedRack = null;
        this.dragging = false;
        
        this.stats = {
            total: 0,
            used: 0,
            empty: 0,
            usageRate: 0
        };
        
        // 创建面板
        this.createPanels();
        
        // 添加射线检测器用于点击
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();
        
        // 记录当前选中的机柜
        this.selectedRack = null;
        this.doorOpen = false;
        
        // 添加双击检测
        this.lastClickTime = 0;
        this.doorState = {
            left: false,
            right: false
        };
        
        // 绑定事件处理方法到实例
        this.onMouseDown = this.onMouseDown.bind(this);
        this.onDoubleClick = this.onDoubleClick.bind(this);
        this.onContainerClick = this.onContainerClick.bind(this);
        
        // 绑定事件监听
        this.container.addEventListener('mousedown', this.onMouseDown);
        this.container.addEventListener('dblclick', this.onDoubleClick);
        this.container.addEventListener('click', this.onContainerClick);
        
        // 添加拖拽状态控制
        this.dragEnabled = false;
        
        // 创建工具栏
        this.createToolbar();
    }

    // 创建工具栏
    createToolbar() {
        const toolbar = document.createElement('div');
        toolbar.className = 'room3d-toolbar';
        toolbar.innerHTML = `
            <button id="toggleDrag" class="toolbar-btn btn-sm">
                <i class="fa fa-arrows"></i>
                <span>启用拖拽</span>
            </button>
            <!-- 可以添加更多工具按钮 -->
        `;

        // 添加工具栏和面板样式
        const style = document.createElement('style');
        style.textContent = `
            .room3d-toolbar {
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 40px;
                background: rgba(255, 255, 255, 0.95);
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                display: flex;
                align-items: center;
                padding: 0 20px;
                z-index: 100;
            }
            
            .toolbar-btn.btn-sm {
                display: flex;
                align-items: center;
                gap: 6px;
                padding: 4px 12px;
                font-size: 12px;
                border: none;
                border-radius: 3px;
                background: #f0f0f0;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            
            .toolbar-btn.btn-sm:hover {
                background: #e0e0e0;
            }
            
            .toolbar-btn.btn-sm.active {
                background: #4CAF50;
                color: white;
            }
            
            .toolbar-btn.btn-sm i {
                font-size: 14px;
            }

            /* 调整统计面板位置 */
            .rack-stats {
                position: absolute;
                top: 60px;
                right: 20px;
                width: 200px;
                background: rgba(255, 255, 255, 0.95);
                padding: 15px;
                border-radius: 5px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                z-index: 1001;
            }

            /* 机柜详情面板样式 */
            .rack-details-panel {
                position: absolute;
                top: 260px;
                right: 20px;
                width: 420px;
                background: rgba(255, 255, 255, 0.95);
                border-radius: 5px;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                padding: 15px;
                z-index: 1000;
                display: none;
            }

            /* 当显示详情面板时的样式 */
            .rack-details-panel.visible {
                display: block;
            }

            .panel-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 12px;
                padding-bottom: 8px;
                border-bottom: 1px solid #eee;
            }

            .panel-header h3 {
                margin: 0;
                font-size: 16px;
                font-weight: bold;
            }

            .rack-info {
                display: flex;
                gap: 20px;
                margin-bottom: 12px;
                color: #666;
                font-size: 13px;
            }

            .devices-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 13px;
            }

            .devices-table th,
            .devices-table td {
                padding: 8px;
                text-align: left;
                border-bottom: 1px solid #eee;
                white-space: nowrap;
            }

            .devices-table th {
                background: #f5f5f5;
                font-weight: 500;
                color: #333;
            }

            /* 调整列宽度比例 */
            .devices-table th:nth-child(1) { width: 45%; }  /* 设备名称列 */
            .devices-table th:nth-child(2) { width: 35%; }  /* 类型列 */
            .devices-table th:nth-child(3) { width: 20%; }  /* 状态列 */

            .devices-table td {
                color: #444;
            }

            .no-devices {
                color: #666;
                text-align: center;
                padding: 15px;
                font-style: italic;
            }

            .close-btn {
                background: none;
                border: none;
                font-size: 18px;
                cursor: pointer;
                padding: 4px 8px;
                color: #999;
            }

            .close-btn:hover {
                color: #333;
            }
        `;
        document.head.appendChild(style);

        // 添加工具栏到容器
        this.container.appendChild(toolbar);

        // 绑定拖拽切换按钮事件
        const toggleDragBtn = document.getElementById('toggleDrag');
        toggleDragBtn.addEventListener('click', () => {
            this.dragEnabled = !this.dragEnabled;
            toggleDragBtn.classList.toggle('active');
            toggleDragBtn.querySelector('span').textContent = 
                this.dragEnabled ? '禁用拖拽' : '启用拖拽';
            
            if (this.dragControls) {
                this.dragControls.enabled = this.dragEnabled;
            }
        });
    }

    // 添加鼠标按下事件处理方法
    onMouseDown(event) {
        // 处理鼠标按下事件
        console.log('Mouse down:', event);
    }

    async init() {
        try {
            // 初始化基础组件
            this.initScene();
            this.initRenderer();
            this.initCamera();
            this.initControls();
            
            // 加载数据并渲染
            await this.loadData();
            this.createFloor();
            this.renderRoom();
            this.renderRacks();
            
            // 更新统计数
            this.updateStats();
            
            // 添加拖拽控制器
            this.initDragControls();
            
            // 开始动画循环
            this.animate();
            
            // 添加窗口大小调整监听
            window.addEventListener('resize', () => this.handleResize());
            
        } catch (error) {
            console.error('初始化失败:', error);
        }
    }

    initScene() {
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0xf0f0f0);

        // 添加环境光
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        this.scene.add(ambientLight);

        // 添加方向光
        const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
        dirLight.position.set(10, 10, 10);
        this.scene.add(dirLight);

        // 添加坐标轴辅助器（用于调试）
        const axesHelper = new THREE.AxesHelper(5);
        this.scene.add(axesHelper);
    }

    initRenderer() {
        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.renderer.setPixelRatio(window.devicePixelRatio);
        this.container.appendChild(this.renderer.domElement);
    }

    initCamera() {
        const aspect = this.container.clientWidth / this.container.clientHeight;
        this.camera = new THREE.PerspectiveCamera(45, aspect, 0.1, 1000);
        
        // 调整相机位置，使场景位于页面上方
        this.camera.position.set(10, 8, 20);  // 降低相机高度
        this.camera.lookAt(0, 0, 0);  // 视点回到原点
    }

    initControls() {
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.screenSpacePanning = false;
        this.controls.minDistance = 5;
        this.controls.maxDistance = 100;
        this.controls.maxPolarAngle = Math.PI / 2;
        
        // 调整控制器目标点
        this.controls.target.set(0, 0, 0);  // 目标点回到原点
        this.controls.update();
    }

    async loadData() {
        try {
            const response = await fetch(this.dataUrl);
            if (!response.ok) throw new Error('数据加载失败');
            
            const data = await response.json();
            console.log('原始数据:', data);
            
            // 验证和清理数据
            this.roomData = {
                room: {
                    ...data.room,
                    dimensions: {
                        width: parseFloat(data.room.dimensions.width) || 1000,
                        length: parseFloat(data.room.dimensions.length) || 2000,
                        height: parseFloat(data.room.dimensions.height) || 450
                    }
                },
                racks: data.racks.map(rack => ({
                    id: rack.id,
                    name: rack.name,
                    width: parseFloat(rack.dimensions.width) || 60,
                    height: parseFloat(rack.dimensions.height) || 200,
                    depth: parseFloat(rack.dimensions.depth) || 120,
                    position_x: parseFloat(rack.position.x) || 0,
                    position_y: parseFloat(rack.position.y) || 0,
                    position_z: parseFloat(rack.position.z) || 0,
                    status: rack.status
                }))
            };
            
            console.log('处理后的数据:', this.roomData);
        } catch (error) {
            console.error('加载数据失败:', error);
            throw error;
        }
    }

    createFloor() {
        if (!this.roomData?.room?.dimensions) return;
        
        const dimensions = this.roomData.room.dimensions;
        const width = dimensions.width / 100;  // 转换为米
        const length = dimensions.length / 100;
        
        const geometry = new THREE.PlaneGeometry(width, length);
        const material = new THREE.MeshStandardMaterial({
            color: 0xcccccc,
            roughness: 0.7,
        });
        
        const floor = new THREE.Mesh(geometry, material);
        floor.rotation.x = -Math.PI / 2;
        floor.position.y = 0;
        this.scene.add(floor);
    }

    renderRoom() {
        if (!this.roomData?.room?.dimensions) return;
        
        const dimensions = this.roomData.room.dimensions;
        const width = dimensions.width / 100;
        const height = dimensions.height / 100;
        const length = dimensions.length / 100;
        
        const geometry = new THREE.BoxGeometry(width, height, length);
        const material = new THREE.MeshBasicMaterial({
            color: 0xcccccc,
            transparent: true,
            opacity: 0.1,
            side: THREE.BackSide
        });
        
        const room = new THREE.Mesh(geometry, material);
        room.position.y = height / 2;
        this.scene.add(room);
    }

    renderRacks() {
        if (!this.roomData?.racks) {
            console.error('没有机柜数据');
            return;
        }
        
        this.roomData.racks.forEach(rackData => {
            const rack = this.createRack(rackData);
            this.scene.add(rack);
            this.rackObjects.set(rackData.id, rack);
        });

        // 更新统计信息
        this.updateStats();
    }

    createRack(rackData) {
        // 建机柜组
        const rackGroup = new THREE.Group();
        
        // 使用后台数据的尺寸（转换为米）
        const width = rackData.width / 100;
        const height = rackData.height / 100;
        const depth = rackData.depth / 100;
        
        // 创建机柜主体
        const frameGeometry = new THREE.BoxGeometry(width, height, depth);
        const frameMaterial = new THREE.MeshPhongMaterial({
            color: this.getRackColor(rackData.status),
            transparent: true,
            opacity: 0.9
        });
        const frame = new THREE.Mesh(frameGeometry, frameMaterial);
        
        // 添加到机柜组
        rackGroup.add(frame);
        
        // 设置机柜组位置
        rackGroup.position.set(
            rackData.position_x / 100,
            height / 2,
            rackData.position_z / 100
        );
        
        // 添加机柜信息
        rackGroup.userData = {
            id: rackData.id,
            name: rackData.name,
            status: rackData.status,
            isRack: true,
            dimensions: { width, height, depth }
        };
        
        // 添加标签
        this.addRackLabel(rackGroup, rackData.name);
        
        return rackGroup;
    }

    // 添加获取机柜颜色的方法
    getRackColor(status) {
        const colors = {
            'empty': 0x999999,  // 浅灰色
            'used': 0x4CAF50,   // 绿色
            'reserved': 0xFFC107,// 黄色
            'maintenance': 0xFF5722, // 橙色
            'default': 0x666666 // 默认深灰色
        };
        return colors[status] || colors.default;
    }

    // 添加机柜标的方法
    addRackLabel(rack, name) {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        canvas.width = 256;
        canvas.height = 64;
        
        // 添加背景色
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'; // 半透明黑色背景
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        // 添加文字
        ctx.fillStyle = 'white';  // 白色文字
        ctx.font = 'bold 36px Arial';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(name, canvas.width / 2, canvas.height / 2);
        
        const texture = new THREE.CanvasTexture(canvas);
        const spriteMaterial = new THREE.SpriteMaterial({ 
            map: texture,
            transparent: true
        });
        const sprite = new THREE.Sprite(spriteMaterial);
        
        // 调整标签大小和位置
        sprite.scale.set(1, 0.25, 1);
        sprite.position.set(0, rack.userData.dimensions.height/2 + 0.3, 0);  // 位于机柜顶部上方
        
        rack.add(sprite);
    }

    handleResize() {
        if (!this.camera || !this.renderer) return;
        
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;
        
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        
        if (this.controls && !this.dragging) {
            this.controls.update();
        }
        
        if (this.renderer && this.scene && this.camera) {
            this.renderer.render(this.scene, this.camera);
        }
    }

    // 修改拖拽控制器初始化
    initDragControls() {
        const rackGroups = Array.from(this.rackObjects.values());
        
        this.dragControls = new THREE.DragControls(rackGroups, this.camera, this.renderer.domElement);
        this.dragControls.enabled = false;
        
        this.dragControls.addEventListener('dragstart', (event) => {
            if (!this.dragEnabled) return;
            
            this.dragging = true;
            this.selectedRack = event.object;
            this.controls.enabled = false;
            
            // 记录初始位置
            this.selectedRack.userData.startPosition = {
                x: this.selectedRack.position.x,
                y: this.selectedRack.position.y,
                z: this.selectedRack.position.z
            };
        });

        this.dragControls.addEventListener('drag', (event) => {
            if (!this.dragEnabled || !this.selectedRack) return;
            
            const rackGroup = event.object;
            
            // 保持Y轴不变
            rackGroup.position.y = rackGroup.userData.startPosition.y;
            
            // 网格吸附
            const gridSize = 0.6; // 60cm
            rackGroup.position.x = Math.round(rackGroup.position.x / gridSize) * gridSize;
            rackGroup.position.z = Math.round(rackGroup.position.z / gridSize) * gridSize;
            
            // 限制在间范围内
            if (this.roomData?.room) {
                const roomWidth = this.roomData.room.dimensions.width / 100 / 2;
                const roomLength = this.roomData.room.dimensions.length / 100 / 2;
                const rackWidth = rackGroup.userData.dimensions.width / 2;
                const rackDepth = rackGroup.userData.dimensions.depth / 2;
                
                rackGroup.position.x = Math.max(-roomWidth + rackWidth, 
                    Math.min(roomWidth - rackWidth, rackGroup.position.x));
                rackGroup.position.z = Math.max(-roomLength + rackDepth, 
                    Math.min(roomLength - rackDepth, rackGroup.position.z));
            }
        });

        this.dragControls.addEventListener('dragend', () => {
            if (!this.dragEnabled || !this.selectedRack) return;
            
            this.controls.enabled = true;
            
            // 更新位置到后台
            this.updateRackPosition(this.selectedRack.userData.id, {
                x: this.selectedRack.position.x * 100,
                y: this.selectedRack.position.y * 100,
                z: this.selectedRack.position.z * 100
            });
            
            this.dragging = false;
            this.selectedRack = null;
        });
    }

    // 添加获取CSRF token的方法
    getCSRFToken() {
        // 首先尝试从cookie中获取
        const name = 'csrftoken';
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // 修改更新位置的方法
    async updateRackPosition(rackId, position) {
        try {
            const csrfToken = this.getCSRFToken();
            
            // 确保发送的是数字类型
            const positionData = {
                x: Number(position.x),
                y: Number(position.y),
                z: Number(position.z)
            };
            
            console.log('发送位置数据:', positionData);

            const response = await fetch(`/api/racks/${rackId}/position/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken || ''
                },
                body: JSON.stringify({
                    position: positionData
                })
            });

            const data = await response.json();
            console.log('服务器响应:', data);

            if (!response.ok || data.status === 'error') {
                throw new Error(data.message || '更新失败');
            }

            console.log('位置更新成功:', data.data);
            
            // 如果状态有变化，更新统计
            if (data.data.status !== this.roomData.racks.find(r => r.id === rackId)?.status) {
                this.updateStats();
            }
        } catch (error) {
            console.error('更新机柜位置失败:', error);
            // 恢复原始位置
            if (this.selectedRack && this.selectedRack.userData.startPosition) {
                this.selectedRack.position.x = this.selectedRack.userData.startPosition.x;
                this.selectedRack.position.z = this.selectedRack.userData.startPosition.z;
            }
        }
    }

    // 修改更新统计的方法
    updateStats() {
        if (!this.roomData?.racks) return;

        this.stats.total = this.roomData.racks.length;
        this.stats.used = this.roomData.racks.filter(rack => rack.status === 'used').length;
        this.stats.empty = this.stats.total - this.stats.used;
        this.stats.usageRate = this.stats.total > 0 
            ? Math.round((this.stats.used / this.stats.total) * 100) 
            : 0;

        // 更新DOM
        document.getElementById('total-racks').textContent = this.stats.total;
        document.getElementById('used-racks').textContent = this.stats.used;
        document.getElementById('empty-racks').textContent = this.stats.empty;
        document.getElementById('usage-rate').textContent = `${this.stats.usageRate}%`;
    }

    // 添加刷新数据的方法
    async refreshData() {
        await this.loadData();
        this.updateStats();
    }

    // 添加点击事件处理
    onContainerClick(event) {
        // 计算鼠标位置
        const rect = this.container.getBoundingClientRect();
        this.mouse.x = ((event.clientX - rect.left) / this.container.clientWidth) * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top) / this.container.clientHeight) * 2 + 1;

        // 更新射线
        this.raycaster.setFromCamera(this.mouse, this.camera);

        // 获取所有机柜对象
        const rackObjects = Array.from(this.rackObjects.values());
        const intersects = this.raycaster.intersectObjects(rackObjects, true);

        if (intersects.length > 0) {
            // 找到最近的机柜对象
            const clickedObject = intersects[0].object;
            const rackGroup = clickedObject.parent;
            
            if (rackGroup && rackGroup.userData.isRack) {
                this.handleRackClick(rackGroup);
            }
        }
    }

    // 处理机柜点击
    handleRackClick(rackGroup) {
        const rackId = rackGroup.userData.id;
        console.log('点击机柜:', rackId);

        // 如果点击的是同一个机柜，切换门的状态
        if (this.selectedRack === rackGroup) {
            this.toggleDoor(rackGroup);
        } else {
            // 如果之有选中的机柜，关闭它的门
            if (this.selectedRack) {
                this.closeDoor(this.selectedRack);
            }
            
            // 更新选中的机柜
            this.selectedRack = rackGroup;
            
            // 获取并显示机柜详情
            this.showRackDetails(rackId);
        }
    }

    // 切换门的状态
    toggleDoor(rackGroup) {
        const doorGroup = rackGroup.children.find(child => child.userData.isDoor);
        if (!doorGroup) return;

        const isOpen = this.doorState.left;
        
        if (isOpen) {
            this.closeDoor(rackGroup);
        } else {
            this.openDoor(rackGroup);
        }
    }

    // 修改开门动画
    openDoor(rackGroup) {
        const doorGroup = rackGroup.children.find(child => child.userData.isDoor);
        if (!doorGroup) return;

        const duration = 1000;
        const startRotation = doorGroup.rotation.y;
        const targetRotation = -Math.PI * 0.8; // 向左打开
        const startTime = Date.now();

        const animate = () => {
            const elapsed = Date.now() - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            const easeProgress = 1 - Math.pow(1 - progress, 3);
            doorGroup.rotation.y = startRotation + (targetRotation - startRotation) * easeProgress;

            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                this.doorState.left = true;
            }
        };

        animate();
    }

    // 修改关门动画
    closeDoor(rackGroup) {
        const doorGroup = rackGroup.children.find(child => child.userData.isDoor);
        if (!doorGroup) return;

        const duration = 1000;
        const startRotation = doorGroup.rotation.y;
        const targetRotation = 0;
        const startTime = Date.now();

        const animate = () => {
            const elapsed = Date.now() - startTime;
            const progress = Math.min(elapsed / duration, 1);

            const easeProgress = 1 - Math.pow(1 - progress, 3);
            doorGroup.rotation.y = startRotation + (targetRotation - startRotation) * easeProgress;

            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                this.doorState.left = false;
            }
        };

        animate();
    }

    // 显示机柜详情
    async showRackDetails(rackId) {
        try {
            const response = await fetch(`/api/racks/${rackId}/details/`);
            if (!response.ok) throw new Error('获取机柜详情失败');
            
            const data = await response.json();
            this.updateRackDetailsPanel(data);
        } catch (error) {
            console.error('获取机柜详情失败:', error);
        }
    }

    // 更新机柜详情面板
    updateRackDetailsPanel(data) {
        const detailsPanel = document.getElementById('rack-details-panel');
        if (!detailsPanel) return;

        detailsPanel.innerHTML = `
            <div class="panel-header">
                <h3>${data.name}</h3>
                <button class="close-btn">&times;</button>
            </div>
            <div class="rack-info">
                <span>状态: ${data.status}</span>
                <span>设备数量: ${data.devices?.length || 0}</span>
            </div>
            <div class="devices-list">
                ${this.renderDevicesList(data.devices)}
            </div>
        `;

        // 显示面板
        detailsPanel.style.display = 'block';

        // 添加关闭按钮事件
        detailsPanel.querySelector('.close-btn').addEventListener('click', () => {
            detailsPanel.style.display = 'none';
            if (this.selectedRack) {
                this.closeDoor(this.selectedRack);
                this.selectedRack = null;
            }
        });
    }

    // 渲染设备列表
    renderDevicesList(devices) {
        if (!devices || devices.length === 0) {
            return '<p class="no-devices">暂无设备</p>';
        }

        return `
            <table class="devices-table">
                <thead>
                    <tr>
                        <th>设备名称</th>
                        <th>类型</th>
                        <th>状态</th>
                    </tr>
                </thead>
                <tbody>
                    ${devices.map(device => `
                        <tr>
                            <td title="${device.name}">${device.name}</td>
                            <td title="${device.type}">${device.type}</td>
                            <td title="${device.status}">${device.status}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    }

    // 处理双击事件
    onDoubleClick(event) {
        const rect = this.container.getBoundingClientRect();
        this.mouse.x = ((event.clientX - rect.left) / this.container.clientWidth) * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top) / this.container.clientHeight) * 2 + 1;

        this.raycaster.setFromCamera(this.mouse, this.camera);
        
        const rackObjects = Array.from(this.rackObjects.values());
        const intersects = this.raycaster.intersectObjects(rackObjects, true);

        if (intersects.length > 0) {
            const clickedObject = intersects[0].object;
            const rackGroup = clickedObject.parent;
            
            if (rackGroup && rackGroup.userData.isRack) {
                // 根据点击位置判断开哪边的门
                const localX = intersects[0].point.x - rackGroup.position.x;
                if (localX < 0) {
                    this.toggleDoor(rackGroup);
                } else {
                    this.toggleDoor(rackGroup);
                }
            }
        }
    }

    // 创建所有面板
    createPanels() {
        // 创建面板容器
        const panelsContainer = document.createElement('div');
        panelsContainer.className = 'room3d-panels';
        this.container.appendChild(panelsContainer);

        // 创建统计面板
        const statsPanel = document.createElement('div');
        statsPanel.className = 'rack-stats';
        statsPanel.innerHTML = `
            <div class="rack-stats-header">机柜统计</div>
            <div class="rack-stats-content">
                <div class="rack-stats-row">
                    <span class="label">总数:</span>
                    <span class="value" id="total-racks">0</span>
                </div>
                <div class="rack-stats-row">
                    <span class="label">已使用:</span>
                    <span class="value" id="used-racks">0</span>
                </div>
                <div class="rack-stats-row">
                    <span class="label">空闲:</span>
                    <span class="value" id="empty-racks">0</span>
                </div>
                <div class="rack-stats-row">
                    <span class="label">使用率:</span>
                    <span class="value" id="usage-rate">0%</span>
                </div>
            </div>
        `;
        panelsContainer.appendChild(statsPanel);

        // 创建机柜详情面板
        const detailsPanel = document.createElement('div');
        detailsPanel.id = 'rack-details-panel';
        detailsPanel.className = 'rack-details-panel';
        panelsContainer.appendChild(detailsPanel);
    }
}

// 添加定时刷新功能（可选）
setInterval(() => {
    if (window.room3dRenderer) {
        window.room3dRenderer.refreshData();
    }
}, 30000); // 每30秒刷新一次 