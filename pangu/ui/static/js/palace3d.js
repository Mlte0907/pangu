/**
 * 盘古 3D 记忆宫殿可视化
 * 使用 Three.js 实现记忆宫殿的3D交互式探索
 */

class Palace3D {
    constructor(containerId, canvasId) {
        this.container = document.getElementById(containerId);
        this.canvas = document.getElementById(canvasId);
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.raycaster = new THREE.Raycaster();
        this.mouse = new THREE.Vector2();
        this.objects = [];
        this.labels = [];
        this.selectedObject = null;
        this.showLabels = true;
        this.init();
    }

    init() {
        // 场景
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x0f0f1a);
        this.scene.fog = new THREE.Fog(0x0f0f1a, 10, 50);

        // 相机
        this.camera = new THREE.PerspectiveCamera(
            60,
            this.container.clientWidth / this.container.clientHeight,
            0.1,
            1000
        );
        this.camera.position.set(0, 5, 15);

        // 渲染器
        this.renderer = new THREE.WebGLRenderer({
            canvas: this.canvas,
            antialias: true,
            alpha: true
        });
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
        this.renderer.setPixelRatio(window.devicePixelRatio);

        // 光照
        const ambientLight = new THREE.AmbientLight(0x404040, 0.5);
        this.scene.add(ambientLight);

        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight.position.set(5, 10, 5);
        this.scene.add(directionalLight);

        const pointLight = new THREE.PointLight(0x6c5ce7, 1, 20);
        pointLight.position.set(0, 5, 0);
        this.scene.add(pointLight);

        // 网格地面
        const gridHelper = new THREE.GridHelper(30, 30, 0x2a2a4a, 0x1a1a2e);
        this.scene.add(gridHelper);

        // 粒子背景
        this.createParticles();

        // 控制器
        this.setupControls();

        // 事件监听
        this.setupEvents();

        // 动画循环
        this.animate();
    }

    createParticles() {
        const particleCount = 500;
        const positions = new Float32Array(particleCount * 3);
        const colors = new Float32Array(particleCount * 3);

        for (let i = 0; i < particleCount * 3; i += 3) {
            positions[i] = (Math.random() - 0.5) * 50;
            positions[i + 1] = Math.random() * 20;
            positions[i + 2] = (Math.random() - 0.5) * 50;

            colors[i] = 0.42 + Math.random() * 0.2;
            colors[i + 1] = 0.36 + Math.random() * 0.2;
            colors[i + 2] = 0.91;
        }

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

        const material = new THREE.PointsMaterial({
            size: 0.05,
            vertexColors: true,
            transparent: true,
            opacity: 0.6
        });

        const particles = new THREE.Points(geometry, material);
        this.scene.add(particles);
    }

    setupControls() {
        // 简单的轨道控制
        let isDragging = false;
        let previousMousePosition = { x: 0, y: 0 };

        this.canvas.addEventListener('mousedown', (e) => {
            isDragging = true;
            previousMousePosition = { x: e.clientX, y: e.clientY };
        });

        this.canvas.addEventListener('mousemove', (e) => {
            if (!isDragging) return;

            const deltaMove = {
                x: e.clientX - previousMousePosition.x,
                y: e.clientY - previousMousePosition.y
            };

            const rotationSpeed = 0.005;
            this.camera.position.x = this.camera.position.x * Math.cos(deltaMove.x * rotationSpeed) -
                                     this.camera.position.z * Math.sin(deltaMove.x * rotationSpeed);
            this.camera.position.z = this.camera.position.x * Math.sin(deltaMove.x * rotationSpeed) +
                                     this.camera.position.z * Math.cos(deltaMove.x * rotationSpeed);

            this.camera.lookAt(0, 0, 0);
            previousMousePosition = { x: e.clientX, y: e.clientY };
        });

        this.canvas.addEventListener('mouseup', () => {
            isDragging = false;
        });

        this.canvas.addEventListener('wheel', (e) => {
            const zoomSpeed = 0.1;
            const direction = e.deltaY > 0 ? 1 : -1;
            this.camera.position.multiplyScalar(1 + direction * zoomSpeed);
            this.camera.lookAt(0, 0, 0);
        });
    }

    setupEvents() {
        window.addEventListener('resize', () => this.onResize());
        this.canvas.addEventListener('click', (e) => this.onClick(e));
        this.canvas.addEventListener('mousemove', (e) => this.onMouseMove(e));
    }

    onResize() {
        this.camera.aspect = this.container.clientWidth / this.container.clientHeight;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(this.container.clientWidth, this.container.clientHeight);
    }

    onClick(event) {
        const rect = this.canvas.getBoundingClientRect();
        this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

        this.raycaster.setFromCamera(this.mouse, this.camera);
        const intersects = this.raycaster.intersectObjects(this.objects);

        if (intersects.length > 0) {
            this.selectedObject = intersects[0].object;
            this.showObjectInfo(this.selectedObject);
        }
    }

    onMouseMove(event) {
        const rect = this.canvas.getBoundingClientRect();
        this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

        this.raycaster.setFromCamera(this.mouse, this.camera);
        const intersects = this.raycaster.intersectObjects(this.objects);

        this.objects.forEach(obj => {
            if (obj.material && obj.material.emissive) {
                obj.material.emissive.setHex(0x000000);
            }
        });

        if (intersects.length > 0) {
            const obj = intersects[0].object;
            if (obj.material && obj.material.emissive) {
                obj.material.emissive.setHex(0x333333);
            }
            this.canvas.style.cursor = 'pointer';
        } else {
            this.canvas.style.cursor = 'default';
        }
    }

    showObjectInfo(object) {
        const info = document.getElementById('palace3d-info');
        if (object.userData) {
            const data = object.userData;
            info.innerHTML = `
                <div class="info-panel">
                    <h4>${data.name || '未命名'}</h4>
                    <p><strong>类型:</strong> ${data.type || '未知'}</p>
                    <p><strong>内容:</strong> ${data.content || '无'}</p>
                    <p><strong>重要性:</strong> ${data.importance || '-'}</p>
                    <p><strong>标签:</strong> ${(data.tags || []).join(', ')}</p>
                </div>
            `;
            info.classList.add('visible');
        }
    }

    loadPalaceData(data) {
        this.clearObjects();

        const wings = data.wings || [];
        const wingSpacing = 6;
        const startX = -(wings.length - 1) * wingSpacing / 2;

        wings.forEach((wing, wingIndex) => {
            const wingX = startX + wingIndex * wingSpacing;
            this.createWing(wing, wingX, 0);

            const rooms = wing.rooms || [];
            rooms.forEach((room, roomIndex) => {
                const roomX = wingX + (roomIndex - (rooms.length - 1) / 2) * 2;
                const roomY = 2 + roomIndex * 0.5;
                this.createRoom(room, roomX, roomY, wing.name);
            });
        });
    }

    createWing(wing, x, z) {
        const geometry = new THREE.BoxGeometry(4, 3, 4);
        const material = new THREE.MeshPhongMaterial({
            color: this.getWingColor(wing.name),
            transparent: true,
            opacity: 0.7,
            wireframe: false
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.position.set(x, 1.5, z);
        mesh.userData = {
            name: wing.name,
            type: 'wing',
            content: wing.description || '',
            importance: wing.importance || 5,
            tags: wing.tags || []
        };

        this.scene.add(mesh);
        this.objects.push(mesh);

        // 添加边框
        const edges = new THREE.EdgesGeometry(geometry);
        const lineMaterial = new THREE.LineBasicMaterial({
            color: this.getWingColor(wing.name),
            transparent: true,
            opacity: 0.8
        });
        const line = new THREE.LineSegments(edges, lineMaterial);
        line.position.copy(mesh.position);
        this.scene.add(line);
    }

    createRoom(room, x, y, wingName) {
        const geometry = new THREE.SphereGeometry(0.5, 16, 16);
        const material = new THREE.MeshPhongMaterial({
            color: this.getRoomColor(room.name),
            transparent: true,
            opacity: 0.8
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.position.set(x, y, 0);
        mesh.userData = {
            name: room.name,
            type: 'room',
            content: room.description || '',
            importance: room.importance || 3,
            tags: room.tags || [],
            wing: wingName
        };

        this.scene.add(mesh);
        this.objects.push(mesh);
    }

    getWingColor(wingName) {
        const colors = {
            'default': 0x6c5ce7,
            'tech': 0x00cec9,
            'personal': 0xfdcb6e,
            'work': 0xff7675,
            'learning': 0x55efc4
        };
        return colors[wingName] || 0x6c5ce7;
    }

    getRoomColor(roomName) {
        const colors = {
            'general': 0xa29bfe,
            'architecture': 0x00cec9,
            'config': 0xfdcb6e,
            'memory-model': 0xff7675,
            'violations': 0xe17055
        };
        return colors[roomName] || 0xa29bfe;
    }

    clearObjects() {
        this.objects.forEach(obj => {
            this.scene.remove(obj);
            if (obj.geometry) obj.geometry.dispose();
            if (obj.material) obj.material.dispose();
        });
        this.objects = [];
    }

    resetCamera() {
        this.camera.position.set(0, 5, 15);
        this.camera.lookAt(0, 0, 0);
    }

    toggleLabels() {
        this.showLabels = !this.showLabels;
    }

    animate() {
        requestAnimationFrame(() => this.animate());

        // 轻微浮动效果
        this.objects.forEach((obj, i) => {
            if (obj.userData.type === 'room') {
                obj.position.y += Math.sin(Date.now() * 0.001 + i) * 0.001;
            }
        });

        this.renderer.render(this.scene, this.camera);
    }

    dispose() {
        this.clearObjects();
        this.renderer.dispose();
    }
}

// 导出
window.Palace3D = Palace3D;
