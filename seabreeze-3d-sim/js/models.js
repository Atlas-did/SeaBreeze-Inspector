// =============================================================================
// SeaBreeze Inspector — 3D 模型构建模块
// 尺寸权威来源: Ryze 官方规格 (Tello 98×92.5×41mm, 桨径76mm)
//              config/arm_config.yaml (臂 L1/L2/L3 = 55/45/35mm, 基座高25mm)
// 场景比例: ×10 (毫米→厘米级显示), 即 SCALE = 0.01 m/mm × 10
// =============================================================================
import * as THREE from 'three';

export const SCALE = 30;                 // visual scale-up (×30, 毫米→场景单位)
export const MM = 0.001 * SCALE;         // 1mm → scene units (0.03)

// ---------- 材质库 ----------
export const MAT = {
  body:     new THREE.MeshStandardMaterial({ color: 0xe8e8e8, roughness: 0.6, metalness: 0.1 }),
  darkGray: new THREE.MeshStandardMaterial({ color: 0x666666, roughness: 0.7, metalness: 0.2 }),
  prop:     new THREE.MeshStandardMaterial({ color: 0x999999, roughness: 0.5, metalness: 0.3 }),
  sensor:   new THREE.MeshStandardMaterial({ color: 0x111111, roughness: 0.3, metalness: 0.6 }),
  armBase:  new THREE.MeshStandardMaterial({ color: 0x4682b4, roughness: 0.5, metalness: 0.3 }),
  link1:    new THREE.MeshStandardMaterial({ color: 0x50c850, roughness: 0.55 }),
  link2:    new THREE.MeshStandardMaterial({ color: 0xdcc83c, roughness: 0.55 }),
  link3:    new THREE.MeshStandardMaterial({ color: 0xe65a3c, roughness: 0.55 }),
  joint:    new THREE.MeshStandardMaterial({ color: 0x404050, roughness: 0.35, metalness: 0.6, emissive: 0x222244, emissiveIntensity: 0.5 }),
  ee:       new THREE.MeshStandardMaterial({ color: 0xff3c3c, roughness: 0.3, emissive: 0x661111 }),
  towerW:   new THREE.MeshStandardMaterial({ color: 0xe8e8e8, roughness: 0.55 }),
  towerR:   new THREE.MeshStandardMaterial({ color: 0xc82828, roughness: 0.55 }),
  nacelle:  new THREE.MeshStandardMaterial({ color: 0xd8d8d8, roughness: 0.5, metalness: 0.2 }),
  blade:    new THREE.MeshStandardMaterial({ color: 0xf0f0f0, roughness: 0.4 }),
};

// =============================================================================
// Tello 无人机 (真实尺寸 ×10)
// =============================================================================
export function buildDrone() {
  const g = new THREE.Group();
  g.name = 'Tello';

  // 机身: 98×41×92.5mm → 0.98×0.41×0.925 场景单位
  const body = new THREE.Mesh(new THREE.BoxGeometry(98 * MM, 41 * MM, 92.5 * MM), MAT.body);
  body.castShadow = true;
  g.add(body);

  // 顶部装饰条 (Tello 标志性顶盖)
  const top = new THREE.Mesh(new THREE.BoxGeometry(70 * MM, 8 * MM, 70 * MM), MAT.darkGray);
  top.position.y = 24 * MM;
  g.add(top);

  // 底部 IR 视觉定位传感器窗口 (椭圆黑色, 底部正中)
  const sensorWin = new THREE.Mesh(new THREE.CylinderGeometry(9 * MM, 9 * MM, 3 * MM, 24), MAT.sensor);
  sensorWin.position.y = -22 * MM;
  g.add(sensorWin);

  // 4 个电机 + 桨叶 + 护罩 (对角线轴距 ~120mm)
  const props = [];
  const motorXY = [[60, 60], [60, -60], [-60, 60], [-60, -60]];   // mm
  for (const [mx, mz] of motorXY) {
    // 电机臂
    const armBar = new THREE.Mesh(new THREE.BoxGeometry(50 * MM, 10 * MM, 14 * MM), MAT.body);
    armBar.position.set(mx * 0.6 * MM, 8 * MM, mz * 0.6 * MM);
    armBar.lookAt(new THREE.Vector3(0, 8 * MM, 0));
    armBar.rotateY(Math.PI / 2);
    g.add(armBar);

    // 电机座
    const motor = new THREE.Mesh(new THREE.CylinderGeometry(10 * MM, 10 * MM, 16 * MM, 16), MAT.darkGray);
    motor.position.set(mx * MM, 14 * MM, mz * MM);
    g.add(motor);

    // 桨叶 (直径 76mm, 两片)
    const prop = new THREE.Group();
    for (const s of [-1, 1]) {
      const bladeMesh = new THREE.Mesh(new THREE.BoxGeometry(76 * MM / 2, 2 * MM, 8 * MM), MAT.prop);
      bladeMesh.position.x = s * 19 * MM;
      prop.add(bladeMesh);
    }
    prop.position.set(mx * MM, 24 * MM, mz * MM);
    g.add(prop);
    props.push(prop);

    // 护罩 (半环)
    const guard = new THREE.Mesh(new THREE.TorusGeometry(45 * MM, 4 * MM, 8, 24, Math.PI), MAT.darkGray);
    guard.position.set(mx * MM, 20 * MM, mz * MM);
    guard.rotation.x = Math.PI / 2;
    guard.rotation.z = Math.atan2(-mz, -mx);
    g.add(guard);
  }

  // ============================
  // 3DOF 机械臂 (挂在机腹)
  // ============================
  const arm = buildArm();
  arm.root.position.y = -41 * MM / 2 - 2 * MM;   // 机腹下方
  g.add(arm.root);

  return { group: g, props, arm };
}

// =============================================================================
// 3DOF 机械臂 — FK 层级: root(yaw θ1) → shoulder(pitch θ2) → elbow(pitch θ3)
// L1=55, L2=45, L3=35mm, 基座高 25mm
// =============================================================================
export function buildArm() {
  const L1 = 55 * MM, L2 = 45 * MM, L3 = 35 * MM, BASE_H = 25 * MM;

  const root = new THREE.Group();   // θ1 底座偏航 (绕Y)
  root.name = 'ArmRoot';

  // 底板 + 基座圆柱
  const plate = new THREE.Mesh(new THREE.CylinderGeometry(35 * MM, 35 * MM, 3 * MM, 24), MAT.armBase);
  root.add(plate);
  const base = new THREE.Mesh(new THREE.CylinderGeometry(25 * MM, 30 * MM, BASE_H, 16), MAT.joint);
  base.position.y = -BASE_H / 2 - 1.25 * MM;
  root.add(base);

  // ---- 肩关节 (θ2, 绕X俯仰) ----
  const shoulder = new THREE.Group();
  shoulder.position.y = -BASE_H - 2.5 * MM;
  root.add(shoulder);
  const sj = new THREE.Mesh(new THREE.SphereGeometry(7 * MM, 16, 12), MAT.joint);
  shoulder.add(sj);

  // L1 大臂 (沿 -Y 向下)
  const link1 = new THREE.Mesh(new THREE.CylinderGeometry(12 * MM, 12 * MM, L1, 16), MAT.link1);
  link1.position.y = -L1 / 2;
  shoulder.add(link1);

  // ---- 肘关节 (θ3, 绕X俯仰) ----
  const elbow = new THREE.Group();
  elbow.position.y = -L1;
  shoulder.add(elbow);
  const ej = new THREE.Mesh(new THREE.SphereGeometry(6 * MM, 16, 12), MAT.joint);
  elbow.add(ej);

  // L2 小臂
  const link2 = new THREE.Mesh(new THREE.CylinderGeometry(10 * MM, 10 * MM, L2, 16), MAT.link2);
  link2.position.y = -L2 / 2;
  elbow.add(link2);

  // L3 末端延伸
  const link3 = new THREE.Mesh(new THREE.CylinderGeometry(8 * MM, 6 * MM, L3, 16), MAT.link3);
  link3.position.y = -L2 - L3 / 2;
  elbow.add(link3);

  // 末端执行器 (红球 + 十字环)
  const ee = new THREE.Group();
  ee.position.y = -L2 - L3;
  elbow.add(ee);
  const eeBall = new THREE.Mesh(new THREE.SphereGeometry(12 * MM, 16, 12), MAT.ee);
  ee.add(eeBall);
  const eeRing = new THREE.Mesh(new THREE.TorusGeometry(16 * MM, 2.5 * MM, 8, 24), MAT.ee);
  ee.add(eeRing);

  /** 设置关节角 (度). θ1∈[0,180], θ2∈[15,165], θ3∈[0,180] */
  function setAngles(t1, t2, t3) {
    root.rotation.y = THREE.MathUtils.degToRad(t1 - 90);   // 90° = 正前方
    shoulder.rotation.x = THREE.MathUtils.degToRad(90 - t2);
    elbow.rotation.x = THREE.MathUtils.degToRad(-t3 + 45);
  }
  setAngles(90, 90, 45);

    // Joint sphere markers for visibility
  const j1Sphere = new THREE.Mesh(new THREE.SphereGeometry(14 * MM, 16, 12),
    new THREE.MeshStandardMaterial({ color: 0xffaa00, roughness: 0.3, emissive: 0x442200, emissiveIntensity: 0.6 }));
  j1Sphere.position.y = -BASE_H - 2.5 * MM;
  root.add(j1Sphere);

  const j2Sphere = new THREE.Mesh(new THREE.SphereGeometry(12 * MM, 16, 12),
    new THREE.MeshStandardMaterial({ color: 0xff8800, roughness: 0.3, emissive: 0x332200, emissiveIntensity: 0.5 }));
  j2Sphere.position.set(0, -L1, 0);
  shoulder.add(j2Sphere);

  return { root, setAngles, ee, links: { L1, L2, L3, BASE_H }, spheres: [j1Sphere, j2Sphere] };
}

// =============================================================================
// 海上风机 (示意比例: 塔高 12, 半径 0.6; 真实 φ3m×30m 会淹没场景)
// =============================================================================
export function buildTurbine() {
  const g = new THREE.Group();
  g.name = 'Turbine';
  const H = 12, R = 0.6;

  // 塔筒 — 红白相间警示条纹 (每 2m 一段)
  const segs = Math.floor(H / 2);
  for (let i = 0; i < segs; i++) {
    const t = new THREE.Mesh(
      new THREE.CylinderGeometry(R * (1 - i * 0.02), R * (1 - (i + 1) * 0.02), 2, 24),
      i % 2 === 0 ? MAT.towerW : MAT.towerR);
    t.position.y = 1 + i * 2;
    t.castShadow = true;
    g.add(t);
  }

  // 机舱
  const nacelle = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.9, 0.9), MAT.nacelle);
  nacelle.position.set(-0.5, H + 0.3, 0);
  nacelle.castShadow = true;
  g.add(nacelle);

  // 轮毂 + 3 叶片
  const rotor = new THREE.Group();
  rotor.position.set(0.4, H + 0.3, 0);
  const hub = new THREE.Mesh(new THREE.SphereGeometry(0.3, 16, 12), MAT.nacelle);
  rotor.add(hub);
  const BLADE_L = 3.2;
  for (let i = 0; i < 3; i++) {
    const b = new THREE.Group();
    const bladeMesh = new THREE.Mesh(new THREE.BoxGeometry(0.06, BLADE_L, 0.28), MAT.blade);
    bladeMesh.position.y = BLADE_L / 2 + 0.2;
    // 叶尖收窄 (用缩放近似翼型)
    bladeMesh.geometry.translate(0, 0, 0);
    b.add(bladeMesh);
    b.rotation.x = (i * 2 * Math.PI) / 3;
    rotor.add(b);
  }
  g.add(rotor);

  // 基础平台 (海上导管架示意)
  const platform = new THREE.Mesh(new THREE.CylinderGeometry(2.2, 2.6, 0.5, 8),
    new THREE.MeshStandardMaterial({ color: 0xc8a028, roughness: 0.7 }));
  platform.position.y = 0.05;
  platform.receiveShadow = true;
  g.add(platform);

  return { group: g, rotor, height: H, radius: R };
}

// =============================================================================
// 环境: 海面 + 雾 + 光照 + 网格
// =============================================================================
export function buildEnvironment(scene) {
  scene.background = new THREE.Color(0x0d2033);
  scene.fog = new THREE.Fog(0x0d2033, 30, 120);

  // 海面
  const sea = new THREE.Mesh(
    new THREE.PlaneGeometry(300, 300),
    new THREE.MeshStandardMaterial({ color: 0x11324a, roughness: 0.85, metalness: 0.1 }));
  sea.rotation.x = -Math.PI / 2;
  sea.position.y = -0.25;
  sea.receiveShadow = true;
  scene.add(sea);

  // 参考网格
  const grid = new THREE.GridHelper(60, 60, 0x2a5a7a, 0x1a3a52);
  grid.position.y = -0.2;
  scene.add(grid);

  // 光照
  const sun = new THREE.DirectionalLight(0xfff4e0, 1.6);
  sun.position.set(15, 25, 10);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -20; sun.shadow.camera.right = 20;
  sun.shadow.camera.top = 20; sun.shadow.camera.bottom = -20;
  scene.add(sun);
  scene.add(new THREE.AmbientLight(0x3a5a78, 0.9));
  const hemi = new THREE.HemisphereLight(0x8ab8d8, 0x0d2033, 0.5);
  scene.add(hemi);

  return { sea };
}

// =============================================================================
// 风粒子 (可视化风向/风速)
// =============================================================================
export function buildWindParticles(scene, count = 200) {
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    pos[i * 3] = (Math.random() - 0.5) * 40;
    pos[i * 3 + 1] = Math.random() * 14;
    pos[i * 3 + 2] = (Math.random() - 0.5) * 40;
  }
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const pts = new THREE.Points(geo, new THREE.PointsMaterial({
    color: 0x88ccff, size: 0.07, transparent: true, opacity: 0.55 }));
  scene.add(pts);
  return pts;
}
