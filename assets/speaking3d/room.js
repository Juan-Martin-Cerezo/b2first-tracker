import * as THREE from '../vendor/three/three.module.min.js';

const VALID_ROLES = new Set(['examiner', 'partner', 'you', null]);
const VALID_SEXES = new Set(['male', 'female']);
const BREATH_HZ = 0.25;
const BREATH_AMP = 0.006;
const MAX_DT = 0.05;
const SPRING_K = 64;
const SPRING_D = 16;
const MAX_YAW = 0.80;
const MAX_YAW_PARTNER = 1.15;
const MAX_YAW_REDUCED = 0.26;
const MAX_PITCH = 0.18;
const MAX_ROLL = 0.04;
const MAX_EYE_YAW = 0.06;
const MAX_EYE_PITCH = 0.04;
const ASSESSOR_PITCH_DOWN = -0.30;
const ASSESSOR_PITCH_GLANCE = -0.08;
const ASSESSOR_YAW_BASE = -0.04;
const ASSESSOR_CYCLE_S = 9.0;
const ASSESSOR_GLANCE_S = 1.2;
const MOUTH_BASE_SCALE = 0.25;
const MOUTH_SCALE_GAIN = 1.9;
const MOUTH_BASE_Y = 0.072;
const MOUTH_DROP_Y = 0.008;
const MOUTH_ATTACK_S = 0.06;
const MOUTH_RELEASE_S = 0.13;
const SILENCE_FLOOR = 4;
const SILENCE_TIMEOUT_S = 0.4;
const FOV_BASE = 58;
const CAM_NEAR = 0.045;

// Camera poses matched to the two-vs-two seating (Photo pair raised/pulled slightly so
// both cards at x=+-0.27 stay inside the frame and clear of all HUD pills at 1280x800 and 390x844)
const CAM_POSES = {
  base: {
    pos: new THREE.Vector3(0.18, 1.22, 0.94),
    target: new THREE.Vector3(0.10, 1.05, -0.55),
    fov: FOV_BASE
  },
  photos: {
    pos: new THREE.Vector3(0.06, 1.20, 0.78),
    target: new THREE.Vector3(0.00, 0.78, 0.18),
    fov: 46
  },
  card: {
    pos: new THREE.Vector3(0.10, 1.14, 0.48),
    target: new THREE.Vector3(0.02, 0.76, 0.09),
    fov: 44
  }
};
const CAM_BASE_POS = CAM_POSES.base.pos;
const CAM_BASE_TARGET = CAM_POSES.base.target;
const _camBaseDir = new THREE.Vector3().subVectors(CAM_BASE_TARGET, CAM_BASE_POS).normalize();
const CAM_BASE_YAW = Math.atan2(-_camBaseDir.x, -_camBaseDir.z);
const CAM_BASE_PITCH = Math.asin(Math.max(-1, Math.min(1, _camBaseDir.y)));

// Camera dolly and reduced-motion lift timing
const DOLLY_WAIT_MS = 900;
const DOLLY_EASE_MS = 800;
const DOLLY_RETURN_MS = 700;
const REDUCED_LIFT_M = 0.10;
const REDUCED_LIFT_MS = 600;
const LIFT_DIR = new THREE.Vector3(0, 0.85, 0.5268).normalize();
const MAX_CACHED_TEXTURES = 4;
const PLACEHOLDER_GREY = 0x9a9a9a;
const PHOTO_BASE_W = 0.17;
const PHOTO_BASE_H = 0.13;
const CARD_BASE_W = 0.289;
const CARD_BASE_H = 0.202;
const PHOTO_L_BASE = new THREE.Vector3(-0.27, 0.748, 0.20);
const PHOTO_R_BASE = new THREE.Vector3(0.27, 0.748, 0.20);
const CARD_BASE_POS = new THREE.Vector3(0, 0.748, 0.03);

// Look-around drag constants (asymmetric yaw: negative = left toward partner, positive = right)
const LOOK_SENS = 0.00465;
const LOOK_YAW_MIN = -1.25;
const LOOK_YAW_MAX = 0.65;
const LOOK_PITCH_MIN = -0.30;
const LOOK_PITCH_MAX = 0.22;
const LOOK_INERTIA_DECAY = 0.90;
const LOOK_INERTIA_STOP = 0.0006;
const LOOK_IDLE_RETURN_S = 2.5;
const LOOK_RETURN_DUR_S = 0.6;
const LOOK_DRAG_TAP_PX = 10;

// Preallocated scratch objects for zero per-frame allocations
const _vHeadWorld = new THREE.Vector3();
const _vTargetWorld = new THREE.Vector3();
const _vLocal = new THREE.Vector3();
const _vCamDir = new THREE.Vector3();
const _vProj = new THREE.Vector3();
const _qInvTorso = new THREE.Quaternion();
const _frustum = new THREE.Frustum();
const _projScreen = new THREE.Matrix4();
const _box3 = new THREE.Box3();
const _raycaster = new THREE.Raycaster();
const _pointerNdc = new THREE.Vector2();

let cachedSupported = null;
let mounted = false;
let container = null;
let renderer = null;
let scene = null;
let camera = null;
let keyLight = null;
let rafId = 0;
let lastMobile = null;
let clockStart = 0;
let lastFrameMs = 0;
let reducedMotionOverride = null;
let prefersReducedMotion = false;
let containerVisible = true;
let contextLost = false;
let speakingData = null;
let silentSec = 0;
let lightboxOpen = false;
let thumbsEl = null;
let thumbsVisible = false;

// Camera dolly runtime state
const camPos = CAM_BASE_POS.clone();
const camTarget = CAM_BASE_TARGET.clone();
let camFov = FOV_BASE;
let dollyGoal = 'base';
let dollyPhase = 'idle';
let dollyStartMs = 0;
let dollyWaitMs = 0;
let dollyDurMs = 0;
const dollyFromPos = CAM_BASE_POS.clone();
const dollyFromTarget = CAM_BASE_TARGET.clone();
let dollyFromFov = FOV_BASE;
let dollyFromWeight = 0;
const dollyToPos = CAM_BASE_POS.clone();
const dollyToTarget = CAM_BASE_TARGET.clone();
let dollyToFov = FOV_BASE;
let dollyToWeight = 0;
let dollyWeight = 0;
let dollyReturnLookYaw = 0;
let dollyReturnLookPitch = 0;

// Reduced-motion material lift state
let matLiftProgress = 0;
let matLiftFrom = 0;
let matLiftTo = 0;
let matLiftStartMs = 0;
let matLiftActive = false;

// Table material props and texture cache
let textureLoader = null;
const textureCache = new Map();
let tableProps = null;
let lightboxBound = false;
let lbCloseListener = null;
let lbBackdropListener = null;
let lbKeyListener = null;

// Look-around runtime state
let lookYaw = 0;
let lookPitch = 0;
let lookVelYaw = 0;
let lookVelPitch = 0;
let lookDragging = false;
let lookReturning = false;
let lookPointerId = null;
let lookStartX = 0;
let lookStartY = 0;
let lookLastX = 0;
let lookLastY = 0;
let lookLastMoveMs = 0;
let lookDragDist = 0;
let lookIdleStartMs = 0;
let lookReturnStartYaw = 0;
let lookReturnStartPitch = 0;
let lookReturnStartMs = 0;
let suppressClickUntil = 0;

// Render timing ring buffer (last 120 frames, zero allocations)
const renderTimes = new Float64Array(120);
let renderTimeIdx = 0;
let renderTimeCount = 0;

let resizeObserver = null;
let intersectionObserver = null;
let motionMql = null;
let motionListener = null;
let overlayObserver = null;
let viewObserver = null;

const state = {
  activeRole: null,
  speakingRole: null,
  speakingAnalyser: null,
  part: 0,
  images: null,
  card: null
};

const castState = {
  partner: { name: 'Alex', sex: 'male' },
  examiner: { name: 'Mr Thompson', sex: 'male' }
};

let avatars = [];
let avatarMap = { examiner: null, partner: null, assessor: null, you: null };
let allFigures = [];
let sceneSharedGeos = null;
let sceneAvatarConfigs = null;

function normalizeSex(value) {
  const s = typeof value === 'string' ? value.trim().toLowerCase() : '';
  return VALID_SEXES.has(s) ? s : 'male';
}

function clamp(v, lo, hi) {
  return v < lo ? lo : (v > hi ? hi : v);
}

function easeInOutCubic(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function buildPhotoStand(basePos, rotYDeg, index, shadows, standMat, backingMat) {
  const grp = new THREE.Group();
  grp.name = index === 0 ? 'photo_left' : 'photo_right';
  grp.position.copy(basePos);
  grp.rotation.y = (rotYDeg * Math.PI) / 180;

  // Slim dark easel stand resting cleanly on the desk pad
  const standBase = new THREE.Mesh(new THREE.BoxGeometry(0.11, 0.006, 0.055), standMat);
  standBase.position.set(0, 0.003, 0);
  standBase.castShadow = shadows;
  standBase.receiveShadow = shadows;
  grp.add(standBase);

  const standLip = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.055, 0.008), standMat);
  standLip.position.set(0, 0.028, -0.018);
  standLip.rotation.x = -0.26;
  standLip.castShadow = shadows;
  grp.add(standLip);

  // Rigid card tilted back 15 degrees so the image faces the candidate cleanly
  const cardPivot = new THREE.Group();
  cardPivot.position.set(0, 0.006, 0);
  cardPivot.rotation.x = (-15 * Math.PI) / 180;
  grp.add(cardPivot);

  const backing = new THREE.Mesh(new THREE.BoxGeometry(0.175, 0.135, 0.004), backingMat);
  backing.position.set(0, 0.0675, 0);
  backing.castShadow = shadows;
  backing.receiveShadow = shadows;
  backing.userData = { materialKind: 'photo', slot: index, materialUrl: '', materialAlt: '' };
  cardPivot.add(backing);

  const faceMat = new THREE.MeshStandardMaterial({
    color: PLACEHOLDER_GREY,
    roughness: 0.82,
    metalness: 0.0
  });
  const face = new THREE.Mesh(new THREE.PlaneGeometry(PHOTO_BASE_W, PHOTO_BASE_H), faceMat);
  face.position.set(0, 0.0675, 0.0024);
  face.castShadow = false;
  face.receiveShadow = false;
  face.userData = { materialKind: 'photo', slot: index, materialUrl: '', materialAlt: '' };
  cardPivot.add(face);

  return { group: grp, basePos: basePos.clone(), backing, face, faceMat };
}

function buildTableMaterials(s, shadows) {
  const standMat = new THREE.MeshStandardMaterial({
    color: 0x26282c,
    roughness: 0.76,
    metalness: 0.14
  });
  const backingMat = new THREE.MeshStandardMaterial({
    color: 0xfaf9f6,
    roughness: 0.86,
    metalness: 0.0
  });

  const photoGroup = new THREE.Group();
  photoGroup.name = 'table_photos';
  photoGroup.visible = false;
  const photoL = buildPhotoStand(PHOTO_L_BASE, 6, 0, shadows, standMat, backingMat);
  const photoR = buildPhotoStand(PHOTO_R_BASE, -6, 1, shadows, standMat, backingMat);
  photoGroup.add(photoL.group);
  photoGroup.add(photoR.group);
  s.add(photoGroup);

  // Part 3 A4 task card: 0.297 x 0.21 x 0.002 m flat on desk pad, rotated 7 deg, centre (0, 0.748, +0.03)
  const cardGroup = new THREE.Group();
  cardGroup.name = 'table_task_card';
  cardGroup.position.copy(CARD_BASE_POS);
  cardGroup.rotation.y = (7 * Math.PI) / 180;
  cardGroup.visible = false;

  const cardBacking = new THREE.Mesh(new THREE.BoxGeometry(0.297, 0.002, 0.21), backingMat);
  cardBacking.position.set(0, 0.001, 0);
  cardBacking.castShadow = shadows;
  cardBacking.receiveShadow = shadows;
  cardBacking.userData = { materialKind: 'card', slot: 0, materialUrl: '', materialAlt: '' };
  cardGroup.add(cardBacking);

  const cardFaceMat = new THREE.MeshStandardMaterial({
    color: PLACEHOLDER_GREY,
    roughness: 0.84,
    metalness: 0.0
  });
  const cardFace = new THREE.Mesh(new THREE.PlaneGeometry(CARD_BASE_W, CARD_BASE_H), cardFaceMat);
  cardFace.position.set(0, 0.0024, 0);
  cardFace.rotation.x = -Math.PI / 2;
  cardFace.castShadow = false;
  cardFace.receiveShadow = false;
  cardFace.userData = { materialKind: 'card', slot: 0, materialUrl: '', materialAlt: '' };
  cardGroup.add(cardFace);

  s.add(cardGroup);

  return {
    photoGroup,
    photos: [photoL, photoR],
    cardGroup,
    cardBasePos: CARD_BASE_POS.clone(),
    cardBacking,
    cardFace,
    cardFaceMat
  };
}

function detectReducedMotion() {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (e) {
    return false;
  }
}

function isReducedMotion() {
  return reducedMotionOverride !== null ? reducedMotionOverride : prefersReducedMotion;
}

function isMobileViewport() {
  if (typeof window === 'undefined') return false;
  const narrow = window.matchMedia ? window.matchMedia('(max-width: 767px)').matches : false;
  const shortH = window.matchMedia ? window.matchMedia('(max-height: 520px)').matches : false;
  const coarse = window.matchMedia ? window.matchMedia('(pointer: coarse)').matches : false;
  const touch = typeof navigator !== 'undefined' && (navigator.maxTouchPoints || 0) > 1;
  return Boolean(narrow || shortH || coarse || touch);
}

function supported() {
  if (cachedSupported !== null) return cachedSupported;
  if (typeof document === 'undefined') {
    cachedSupported = false;
    return false;
  }
  try {
    const canvas = document.createElement('canvas');
    const gl =
      canvas.getContext('webgl2') ||
      canvas.getContext('webgl') ||
      canvas.getContext('experimental-webgl');
    cachedSupported = Boolean(gl);
    if (gl) {
      const ext = gl.getExtension('WEBGL_lose_context');
      if (ext) ext.loseContext();
    }
  } catch (e) {
    cachedSupported = false;
  }
  return cachedSupported;
}

function makeCapsuleBetween(p0, p1, radius, endTrim, radiusScale) {
  const dir = new THREE.Vector3().subVectors(p1, p0);
  const fullLen = Math.max(0.04, dir.length());
  const trim = endTrim || 0;
  const len = Math.max(0.03, fullLen - trim);
  const unit = dir.clone().normalize();
  const pEnd = p0.clone().addScaledVector(unit, len);
  const mid = new THREE.Vector3().addVectors(p0, pEnd).multiplyScalar(0.5);
  const quat = new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 1, 0),
    unit
  );
  // Shared CapsuleGeometry(0.044, 0.2) has total unscaled height 0.288 along Y.
  const scaleY = Math.max(0.25, len / 0.288);
  const rScale = radiusScale || 1;
  const m = new THREE.Matrix4();
  m.compose(mid, quat, new THREE.Vector3(rScale, scaleY, rScale));
  return m;
}

function createTorsoGeometry(sex) {
  // Smooth tapered seated torso from hip (y=0) to collar (y=0.56).
  // Male shoulder width ~0.38 m; female shoulder width ~0.34 m with +6% hip base and tailored waist.
  const isFemale = sex === 'female';
  const pts = isFemale
    ? [
        new THREE.Vector2(0.0, 0.0),
        new THREE.Vector2(0.154, 0.01),
        new THREE.Vector2(0.158, 0.09),
        new THREE.Vector2(0.132, 0.21),
        new THREE.Vector2(0.156, 0.35),
        new THREE.Vector2(0.170, 0.45),
        new THREE.Vector2(0.156, 0.51),
        new THREE.Vector2(0.098, 0.545),
        new THREE.Vector2(0.052, 0.56),
        new THREE.Vector2(0.0, 0.56)
      ]
    : [
        new THREE.Vector2(0.0, 0.0),
        new THREE.Vector2(0.145, 0.01),
        new THREE.Vector2(0.152, 0.14),
        new THREE.Vector2(0.175, 0.34),
        new THREE.Vector2(0.192, 0.45),
        new THREE.Vector2(0.18, 0.51),
        new THREE.Vector2(0.11, 0.545),
        new THREE.Vector2(0.06, 0.56),
        new THREE.Vector2(0.0, 0.56)
      ];
  const geo = new THREE.LatheGeometry(pts, 18);
  geo.scale(1.0, 1.0, isFemale ? 0.57 : 0.58);
  geo.computeVertexNormals();
  return geo;
}

function buildAvatar(cfg, sharedGeos, shadows) {
  const sex = cfg.name === 'assessor' ? 'male' : normalizeSex(cfg.sex);
  const isFemale = sex === 'female';
  const clothColor = cfg.clothPalette ? (cfg.clothPalette[sex] || cfg.clothColor) : cfg.clothColor;
  const ownedGeos = [];
  const ownedMats = [];

  const root = new THREE.Group();
  root.name = cfg.name;
  root.position.set(cfg.pos[0], cfg.pos[1], cfg.pos[2]);
  root.rotation.y = cfg.rotY;

  const skinMat = new THREE.MeshStandardMaterial({
    color: cfg.skinColor,
    roughness: 0.72,
    metalness: 0.02
  });
  const clothMat = new THREE.MeshStandardMaterial({
    color: clothColor,
    roughness: 0.82,
    metalness: 0.03
  });
  const hairMat = new THREE.MeshStandardMaterial({
    color: cfg.hairColor,
    roughness: 0.85,
    metalness: 0.02
  });
  const eyeMat = new THREE.MeshStandardMaterial({
    color: 0x22201e,
    roughness: 0.25,
    metalness: 0.05
  });
  const browMat = new THREE.MeshStandardMaterial({
    color: cfg.hairColor,
    roughness: 0.9,
    metalness: 0.0
  });
  const mouthMat = new THREE.MeshStandardMaterial({
    color: 0x3a2320,
    roughness: 0.75,
    metalness: 0.02
  });
  ownedMats.push(skinMat, clothMat, hairMat, eyeMat, browMat, mouthMat);

  // Breathing group (hips anchored at y=0, scales subtly along Y)
  const torsoGroup = new THREE.Group();
  torsoGroup.name = cfg.name + '_torso';
  if (cfg.leanX) {
    torsoGroup.rotation.x = cfg.leanX;
  }
  root.add(torsoGroup);

  const torsoGeo = createTorsoGeometry(sex);
  ownedGeos.push(torsoGeo);
  const torsoMesh = new THREE.Mesh(torsoGeo, clothMat);
  torsoMesh.castShadow = shadows;
  torsoMesh.receiveShadow = shadows;
  torsoGroup.add(torsoMesh);

  // Arms: 4 capsule segments in one InstancedMesh (upper L/R, lower L/R)
  const armMesh = new THREE.InstancedMesh(sharedGeos.armSeg, clothMat, 4);
  armMesh.castShadow = shadows;
  armMesh.receiveShadow = shadows;
  const pose = cfg.armPose;
  const shScaleX = isFemale ? 0.88 : 1.0;
  const armRadScale = isFemale ? 0.88 : 1.0;
  const shL = new THREE.Vector3(pose.shL.x * shScaleX, pose.shL.y, pose.shL.z);
  const shR = new THREE.Vector3(pose.shR.x * shScaleX, pose.shR.y, pose.shR.z);
  armMesh.setMatrixAt(0, makeCapsuleBetween(shL, pose.elL, 0.04, 0, armRadScale));
  armMesh.setMatrixAt(1, makeCapsuleBetween(pose.elL, pose.hdL, 0.036, 0.032, armRadScale));
  armMesh.setMatrixAt(2, makeCapsuleBetween(shR, pose.elR, 0.04, 0, armRadScale));
  armMesh.setMatrixAt(3, makeCapsuleBetween(pose.elR, pose.hdR, 0.036, 0.032, armRadScale));
  armMesh.instanceMatrix.needsUpdate = true;
  torsoGroup.add(armMesh);

  // Hands: 2 spheres (diameter ~0.07) in one InstancedMesh
  const handsMesh = new THREE.InstancedMesh(sharedGeos.hand, skinMat, 2);
  handsMesh.castShadow = shadows;
  handsMesh.receiveShadow = shadows;
  const hm = new THREE.Matrix4();
  hm.makeTranslation(pose.hdL.x, pose.hdL.y, pose.hdL.z);
  handsMesh.setMatrixAt(0, hm);
  hm.makeTranslation(pose.hdR.x, pose.hdR.y, pose.hdR.z);
  handsMesh.setMatrixAt(1, hm);
  handsMesh.instanceMatrix.needsUpdate = true;
  torsoGroup.add(handsMesh);

  // Neck (tucked cleanly into torso collar and head base with no seam)
  const neckGeo = isFemale
    ? new THREE.CylinderGeometry(0.041, 0.047, 0.11, 12)
    : new THREE.CylinderGeometry(0.048, 0.054, 0.11, 12);
  ownedGeos.push(neckGeo);
  const neckMesh = new THREE.Mesh(neckGeo, skinMat);
  neckMesh.position.set(0, 0.58, 0);
  neckMesh.castShadow = shadows;
  torsoGroup.add(neckMesh);

  // Head group pivoted at neck top (y = 0.61) for gaze turns and nodding
  const headGroup = new THREE.Group();
  headGroup.name = cfg.name + '_head';
  headGroup.position.set(0, 0.61, 0);
  headGroup.rotation.order = 'YXZ';
  torsoGroup.add(headGroup);

  const headScale = isFemale ? 0.95 : 1.0;
  const headMesh = new THREE.Mesh(sharedGeos.head, skinMat);
  headMesh.position.set(0, 0.118, 0);
  headMesh.scale.set(0.095 * headScale, 0.115 * headScale, 0.105 * headScale);
  headMesh.castShadow = shadows;
  headMesh.receiveShadow = shadows;
  headGroup.add(headMesh);

  // Stylized hair cap over upper/back crown (total seated height ~0.90 above hip)
  const hairGeo = isFemale
    ? new THREE.SphereGeometry(1, 18, 14, 0, Math.PI * 2, 0, Math.PI * 0.66)
    : new THREE.SphereGeometry(1, 18, 12, 0, Math.PI * 2, 0, Math.PI * 0.6);
  ownedGeos.push(hairGeo);
  const hairMesh = new THREE.Mesh(hairGeo, hairMat);
  if (isFemale) {
    hairMesh.position.set(0, 0.132, 0.010);
    hairMesh.scale.set(0.099, 0.108, 0.108);
    hairMesh.rotation.x = -0.08;
  } else {
    hairMesh.position.set(0, 0.138, 0.014);
    hairMesh.scale.set(0.099, 0.104, 0.108);
    hairMesh.rotation.x = -0.18;
  }
  hairMesh.castShadow = shadows;
  headGroup.add(hairMesh);

  // Female nape hair volume (+1 mesh, same hairMat, stays clear of chair backrest)
  if (isFemale) {
    const hairBackGeo = new THREE.SphereGeometry(1, 16, 12);
    ownedGeos.push(hairBackGeo);
    const hairBackMesh = new THREE.Mesh(hairBackGeo, hairMat);
    hairBackMesh.name = 'hair_nape';
    hairBackMesh.position.set(0, 0.068, 0.036);
    hairBackMesh.scale.set(0.104, 0.105, 0.088);
    hairBackMesh.castShadow = shadows;
    headGroup.add(hairBackMesh);
  }

  // Eyes (two spheres r=0.012 on -Z front of face, pivoted at head centre for subtle gaze shift)
  const eyesGroup = new THREE.Group();
  eyesGroup.position.set(0, 0.132, 0);
  eyesGroup.rotation.order = 'YXZ';
  const eyesMesh = new THREE.InstancedMesh(sharedGeos.eye, eyeMat, 2);
  const em = new THREE.Matrix4();
  const eyeX = isFemale ? 0.032 : 0.034;
  const eyeZ = isFemale ? -0.089 : -0.094;
  em.makeTranslation(-eyeX, 0, eyeZ);
  eyesMesh.setMatrixAt(0, em);
  em.makeTranslation(eyeX, 0, eyeZ);
  eyesMesh.setMatrixAt(1, em);
  eyesMesh.instanceMatrix.needsUpdate = true;
  eyesGroup.add(eyesMesh);
  headGroup.add(eyesGroup);

  // Brows (two thin boxes; thinner and gently arched for female variant)
  const browGeo = isFemale
    ? new THREE.BoxGeometry(0.030, 0.0042, 0.010)
    : new THREE.BoxGeometry(0.032, 0.007, 0.012);
  ownedGeos.push(browGeo);
  const browsMesh = new THREE.InstancedMesh(browGeo, browMat, 2);
  const bm = new THREE.Matrix4();
  const browTilt = isFemale ? 0.09 : 0.06;
  const browZ = isFemale ? -0.090 : -0.095;
  const qL = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, -browTilt));
  const qR = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, browTilt));
  bm.compose(new THREE.Vector3(-eyeX, 0.153, browZ), qL, new THREE.Vector3(1, 1, 1));
  browsMesh.setMatrixAt(0, bm);
  bm.compose(new THREE.Vector3(eyeX, 0.153, browZ), qR, new THREE.Vector3(1, 1, 1));
  browsMesh.setMatrixAt(1, bm);
  browsMesh.instanceMatrix.needsUpdate = true;
  headGroup.add(browsMesh);

  // Nose (small cone pointing -Z)
  const noseMesh = new THREE.Mesh(sharedGeos.nose, skinMat);
  noseMesh.position.set(0, 0.112, isFemale ? -0.102 : -0.108);
  noseMesh.rotation.x = -Math.PI * 0.48;
  headGroup.add(noseMesh);

  // Mouth (dark thin box scaled at runtime from audio RMS)
  const mouthMesh = new THREE.Mesh(sharedGeos.mouth, mouthMat);
  mouthMesh.name = 'mouth';
  mouthMesh.position.set(0, MOUTH_BASE_Y, isFemale ? -0.092 : -0.097);
  mouthMesh.scale.y = MOUTH_BASE_SCALE;
  headGroup.add(mouthMesh);

  // Optional clipboard for assessor (plain clipboard held in lap, no second table)
  if (cfg.clipboard) {
    const boardMat = new THREE.MeshStandardMaterial({
      color: 0x6f533c,
      roughness: 0.72,
      metalness: 0.06
    });
    const paperMat = new THREE.MeshStandardMaterial({
      color: 0xf4f1ea,
      roughness: 0.9,
      metalness: 0.0
    });
    const boardGeo = new THREE.BoxGeometry(0.24, 0.32, 0.012);
    const paperGeo = new THREE.BoxGeometry(0.21, 0.28, 0.005);
    ownedGeos.push(boardGeo, paperGeo);
    ownedMats.push(boardMat, paperMat);
    const clipGroup = new THREE.Group();
    clipGroup.position.set(0.02, 0.28, -0.34);
    clipGroup.rotation.set(-0.98, 0.08, 0.04);
    const board = new THREE.Mesh(boardGeo, boardMat);
    board.castShadow = shadows;
    clipGroup.add(board);
    const paper = new THREE.Mesh(paperGeo, paperMat);
    paper.position.set(0, -0.004, 0.008);
    clipGroup.add(paper);
    torsoGroup.add(clipGroup);
  }

  const initYaw = cfg.name === 'assessor' ? ASSESSOR_YAW_BASE : 0;
  const initPitch = cfg.name === 'assessor' ? ASSESSOR_PITCH_DOWN : 0;
  headGroup.rotation.set(initPitch, initYaw, 0);

  root.userData = {
    name: cfg.name,
    sex,
    head: headGroup,
    eyes: eyesGroup,
    mouth: mouthMesh,
    jaw: headGroup.getObjectByName('jaw') || null,
    torso: torsoGroup,
    mouthBaseY: MOUTH_BASE_Y,
    phaseOffset: cfg.phaseOffset,
    yaw: initYaw,
    yawVel: 0,
    pitch: initPitch,
    pitchVel: 0,
    roll: 0,
    rollVel: 0,
    eyeYaw: 0,
    eyePitch: 0,
    mouthOpen: 0,
    ownedGeos,
    ownedMats
  };

  return root;
}

function disposeAvatar(avatarRoot) {
  if (!avatarRoot || !avatarRoot.userData) return;
  const geos = avatarRoot.userData.ownedGeos || [];
  const mats = avatarRoot.userData.ownedMats || [];
  for (let i = 0; i < geos.length; i++) {
    try { geos[i].dispose(); } catch (e) {}
  }
  for (let i = 0; i < mats.length; i++) {
    try { mats[i].dispose(); } catch (e) {}
  }
}

function buildCandidateSelf(sharedGeos, shadows) {
  // First-person seated candidate ("you"): hips directly under the camera at (0.18, 0.46, 0.82),
  // forearms/hands resting calmly on the candidate edge of the table without blocking materials.
  const root = new THREE.Group();
  root.name = 'you';
  root.position.set(0.18, 0.46, 0.82);
  root.rotation.y = 0;

  const skinMat = new THREE.MeshStandardMaterial({
    color: 0xdab69b,
    roughness: 0.72,
    metalness: 0.02
  });
  const clothMat = new THREE.MeshStandardMaterial({
    color: 0x3b4d63,
    roughness: 0.84,
    metalness: 0.03
  });

  const pose = {
    shL: new THREE.Vector3(-0.19, 0.44, 0.0),
    elL: new THREE.Vector3(-0.24, 0.31, -0.34),
    hdL: new THREE.Vector3(-0.15, 0.315, -0.58),
    shR: new THREE.Vector3(0.19, 0.44, 0.0),
    elR: new THREE.Vector3(0.26, 0.31, -0.34),
    hdR: new THREE.Vector3(0.24, 0.315, -0.58)
  };

  const armMesh = new THREE.InstancedMesh(sharedGeos.armSeg, clothMat, 4);
  armMesh.castShadow = shadows;
  armMesh.receiveShadow = shadows;
  armMesh.setMatrixAt(0, makeCapsuleBetween(pose.shL, pose.elL, 0.038, 0));
  armMesh.setMatrixAt(1, makeCapsuleBetween(pose.elL, pose.hdL, 0.034, 0.034));
  armMesh.setMatrixAt(2, makeCapsuleBetween(pose.shR, pose.elR, 0.038, 0));
  armMesh.setMatrixAt(3, makeCapsuleBetween(pose.elR, pose.hdR, 0.034, 0.034));
  armMesh.instanceMatrix.needsUpdate = true;
  root.add(armMesh);

  const handsMesh = new THREE.InstancedMesh(sharedGeos.hand, skinMat, 2);
  handsMesh.castShadow = shadows;
  handsMesh.receiveShadow = shadows;
  const hm = new THREE.Matrix4();
  hm.makeTranslation(pose.hdL.x, pose.hdL.y, pose.hdL.z);
  handsMesh.setMatrixAt(0, hm);
  hm.makeTranslation(pose.hdR.x, pose.hdR.y, pose.hdR.z);
  handsMesh.setMatrixAt(1, hm);
  handsMesh.instanceMatrix.needsUpdate = true;
  root.add(handsMesh);

  root.userData = { name: 'you' };
  return root;
}

function buildScene(mobile) {
  const shadows = !mobile;
  const s = new THREE.Scene();
  s.background = new THREE.Color(0xdcd7ce);

  // Lighting
  const hemi = new THREE.HemisphereLight(0xffffff, 0x6b6155, 0.55);
  s.add(hemi);

  const dir = new THREE.DirectionalLight(0xfff4e5, 1.15);
  dir.position.set(2.2, 3.0, 1.6);
  dir.target.position.set(0, 0.74, 0);
  if (shadows) {
    dir.castShadow = true;
    dir.shadow.mapSize.set(1024, 1024);
    dir.shadow.camera.left = -2.4;
    dir.shadow.camera.right = 2.4;
    dir.shadow.camera.top = 2.4;
    dir.shadow.camera.bottom = -2.4;
    dir.shadow.camera.near = 0.5;
    dir.shadow.camera.far = 9.5;
    dir.shadow.bias = -0.0005;
    dir.shadow.normalBias = 0.02;
  }
  s.add(dir);
  s.add(dir.target);
  keyLight = dir;

  const fill = new THREE.PointLight(0xfff8f0, 0.15, 0, 0);
  fill.position.set(0, 1.32, 1.55);
  s.add(fill);

  // Room: 5.0 x 5.2 x 2.6 (w x d x h) so back wall sits cleanly behind the assessor at z=-1.72
  const wallMat = new THREE.MeshStandardMaterial({
    color: 0xe9e6df,
    roughness: 0.92,
    metalness: 0.0
  });
  const floorMat = new THREE.MeshStandardMaterial({
    color: 0x8c8378,
    roughness: 0.88,
    metalness: 0.0
  });

  const floor = new THREE.Mesh(new THREE.PlaneGeometry(5.0, 5.2), floorMat);
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(0, 0, -0.4);
  floor.receiveShadow = shadows;
  s.add(floor);

  const backWall = new THREE.Mesh(new THREE.PlaneGeometry(5.0, 2.6), wallMat);
  backWall.position.set(0, 1.3, -2.55);
  backWall.receiveShadow = shadows;
  s.add(backWall);

  const leftWall = new THREE.Mesh(new THREE.PlaneGeometry(5.2, 2.6), wallMat);
  leftWall.position.set(-2.5, 1.3, -0.4);
  leftWall.rotation.y = Math.PI / 2;
  leftWall.receiveShadow = shadows;
  s.add(leftWall);

  const rightWall = new THREE.Mesh(new THREE.PlaneGeometry(5.2, 2.6), wallMat);
  rightWall.position.set(2.5, 1.3, -0.4);
  rightWall.rotation.y = -Math.PI / 2;
  rightWall.receiveShadow = shadows;
  s.add(rightWall);

  // Subtle skirting board along back wall to ground the room
  const trimMat = new THREE.MeshStandardMaterial({
    color: 0xd4cfc5,
    roughness: 0.88,
    metalness: 0.0
  });
  const baseboard = new THREE.Mesh(new THREE.BoxGeometry(5.0, 0.1, 0.02), trimMat);
  baseboard.position.set(0, 0.05, -2.54);
  s.add(baseboard);

  // Soft ceiling emissive panel at y=2.58
  const panelMat = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    emissive: 0xfff8ee,
    emissiveIntensity: 0.85,
    roughness: 0.5
  });
  const ceilingPanel = new THREE.Mesh(new THREE.PlaneGeometry(1.6, 0.9), panelMat);
  ceilingPanel.position.set(0, 2.58, -0.2);
  ceilingPanel.rotation.x = Math.PI / 2;
  s.add(ceilingPanel);

  // Table: 1.60 x 0.80, top at y=0.74, centred at (0, 0.74, 0), candidate edge z=+0.40
  const woodMat = new THREE.MeshStandardMaterial({
    color: 0xb08a5e,
    roughness: 0.64,
    metalness: 0.04
  });
  const tableTop = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.04, 0.8), woodMat);
  tableTop.position.set(0, 0.72, 0);
  tableTop.castShadow = shadows;
  tableTop.receiveShadow = shadows;
  s.add(tableTop);

  // Four table legs 0.05^2 in one InstancedMesh
  const legGeo = new THREE.BoxGeometry(0.05, 0.7, 0.05);
  const tableLegs = new THREE.InstancedMesh(legGeo, woodMat, 4);
  tableLegs.castShadow = shadows;
  tableLegs.receiveShadow = shadows;
  const legCoords = [
    [-0.72, 0.35, -0.32],
    [0.72, 0.35, -0.32],
    [-0.72, 0.35, 0.32],
    [0.72, 0.35, 0.32]
  ];
  const tm = new THREE.Matrix4();
  legCoords.forEach((c, idx) => {
    tm.makeTranslation(c[0], c[1], c[2]);
    tableLegs.setMatrixAt(idx, tm);
  });
  tableLegs.instanceMatrix.needsUpdate = true;
  s.add(tableLegs);

  // Desk pad: 1.30 x 0.55 at y=0.744, beige 0xd9d2c3
  const padMat = new THREE.MeshStandardMaterial({
    color: 0xd9d2c3,
    roughness: 0.9,
    metalness: 0.0
  });
  const deskPad = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.008, 0.55), padMat);
  deskPad.position.set(0, 0.744, 0);
  deskPad.receiveShadow = shadows;
  s.add(deskPad);

  // Chairs: two-vs-two layout (4 chairs batched into 3 InstancedMeshes; assessor uses plain side chair)
  const seatsCfg = [
    { x: -0.80, z: 0.64, rotY: -0.55 },          // Partner (ahead of candidate shoulder line, turned toward table)
    { x: 0.18, z: 0.82, rotY: 0.0 },             // You (candidate right)
    { x: 0.18, z: -0.86, rotY: Math.PI },        // Examiner (interlocutor at table)
    { x: -0.72, z: -1.46, rotY: Math.PI * 0.94 } // Assessor (behind examiner, offset left)
  ];
  const chairMat = new THREE.MeshStandardMaterial({
    color: 0x4b4f55,
    roughness: 0.76,
    metalness: 0.14
  });
  const seatMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(0.45, 0.04, 0.45), chairMat, 4);
  const backMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(0.45, 0.5, 0.04), chairMat, 4);
  const cLegMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(0.036, 0.42, 0.036), chairMat, 16);
  seatMesh.castShadow = shadows;
  seatMesh.receiveShadow = shadows;
  backMesh.castShadow = shadows;
  backMesh.receiveShadow = shadows;
  cLegMesh.castShadow = shadows;

  const chairBase = new THREE.Matrix4();
  const localMat = new THREE.Matrix4();
  const finalMat = new THREE.Matrix4();
  const cLegOffsets = [
    [-0.19, 0.21, -0.19],
    [0.19, 0.21, -0.19],
    [-0.19, 0.21, 0.19],
    [0.19, 0.21, 0.19]
  ];
  seatsCfg.forEach((ch, i) => {
    chairBase.compose(
      new THREE.Vector3(ch.x, 0, ch.z),
      new THREE.Quaternion().setFromEuler(new THREE.Euler(0, ch.rotY, 0)),
      new THREE.Vector3(1, 1, 1)
    );
    localMat.makeTranslation(0, 0.44, 0);
    finalMat.multiplyMatrices(chairBase, localMat);
    seatMesh.setMatrixAt(i, finalMat);

    localMat.makeTranslation(0, 0.69, 0.21);
    finalMat.multiplyMatrices(chairBase, localMat);
    backMesh.setMatrixAt(i, finalMat);

    cLegOffsets.forEach((o, j) => {
      localMat.makeTranslation(o[0], o[1], o[2]);
      finalMat.multiplyMatrices(chairBase, localMat);
      cLegMesh.setMatrixAt(i * 4 + j, finalMat);
    });
  });
  seatMesh.instanceMatrix.needsUpdate = true;
  backMesh.instanceMatrix.needsUpdate = true;
  cLegMesh.instanceMatrix.needsUpdate = true;
  s.add(seatMesh);
  s.add(backMesh);
  s.add(cLegMesh);

  // Shared base avatar geometries (per-variant torso, neck, hair, brows are built per avatar for clean disposal)
  const sharedGeos = {
    armSeg: new THREE.CapsuleGeometry(0.044, 0.2, 6, 10),
    hand: new THREE.SphereGeometry(0.036, 12, 10),
    head: new THREE.SphereGeometry(1, 20, 16),
    eye: new THREE.SphereGeometry(0.012, 10, 8),
    nose: new THREE.ConeGeometry(0.013, 0.034, 10),
    mouth: new THREE.BoxGeometry(0.046, 0.016, 0.014)
  };
  sceneSharedGeos = sharedGeos;

  // Two-vs-two exam geometry: examiner + assessor facing partner + candidate ("you")
  const avatarConfigs = [
    {
      name: 'examiner',
      pos: [0.18, 0.46, -0.86],
      rotY: Math.PI,
      leanX: -0.05,
      skinColor: 0xd8b49a,
      clothColor: 0x2f3d56,
      clothPalette: { male: 0x2f3d56, female: 0x513f56 },
      hairColor: 0x524b46,
      phaseOffset: 0.0,
      clipboard: false,
      armPose: {
        shL: new THREE.Vector3(-0.17, 0.45, 0.0),
        elL: new THREE.Vector3(-0.22, 0.30, -0.22),
        hdL: new THREE.Vector3(-0.14, 0.335, -0.48),
        shR: new THREE.Vector3(0.17, 0.45, 0.0),
        elR: new THREE.Vector3(0.22, 0.30, -0.22),
        hdR: new THREE.Vector3(0.14, 0.335, -0.48)
      }
    },
    {
      name: 'partner',
      pos: [-0.80, 0.46, 0.64],
      rotY: -0.55,
      leanX: -0.05,
      skinColor: 0xdfbda5,
      clothColor: 0x6b7350,
      clothPalette: { male: 0x6b7350, female: 0x7a5b6b },
      hairColor: 0x4b3525,
      phaseOffset: 2.1,
      clipboard: false,
      armPose: {
        // Forearms resting cleanly on the candidate edge of the table (turned toward the table)
        shL: new THREE.Vector3(-0.17, 0.45, 0.0),
        elL: new THREE.Vector3(-0.21, 0.31, -0.24),
        hdL: new THREE.Vector3(-0.12, 0.33, -0.46),
        shR: new THREE.Vector3(0.17, 0.45, 0.0),
        elR: new THREE.Vector3(0.21, 0.31, -0.26),
        hdR: new THREE.Vector3(0.16, 0.335, -0.50)
      }
    },
    {
      name: 'assessor',
      pos: [-0.72, 0.46, -1.46],
      rotY: Math.PI * 0.94,
      leanX: 0,
      skinColor: 0xcfa88d,
      clothColor: 0x5b5b5b,
      hairColor: 0x3b312a,
      phaseOffset: 4.2,
      clipboard: true,
      armPose: {
        shL: new THREE.Vector3(-0.17, 0.45, 0.0),
        elL: new THREE.Vector3(-0.21, 0.25, -0.14),
        hdL: new THREE.Vector3(-0.10, 0.28, -0.34),
        shR: new THREE.Vector3(0.17, 0.45, 0.0),
        elR: new THREE.Vector3(0.20, 0.26, -0.15),
        hdR: new THREE.Vector3(0.10, 0.30, -0.32)
      }
    }
  ];
  sceneAvatarConfigs = {
    examiner: avatarConfigs[0],
    partner: avatarConfigs[1],
    assessor: avatarConfigs[2]
  };

  avatarMap = { examiner: null, partner: null, assessor: null, you: null };
  avatars = avatarConfigs.map(cfg => {
    const builtCfg = (cfg.name === 'examiner' || cfg.name === 'partner')
      ? Object.assign({}, cfg, { sex: castState[cfg.name].sex })
      : cfg;
    const grp = buildAvatar(builtCfg, sharedGeos, shadows);
    avatarMap[cfg.name] = grp;
    s.add(grp);
    return grp;
  });

  const youGrp = buildCandidateSelf(sharedGeos, shadows);
  avatarMap.you = youGrp;
  s.add(youGrp);
  allFigures = avatars.concat([youGrp]);

  tableProps = buildTableMaterials(s, shadows);

  return s;
}

function isSpeakingOverlayClosed() {
  if (typeof document === 'undefined') return false;
  const ov = document.getElementById('speakingOverlay');
  if (ov && !ov.classList.contains('is-open')) return true;
  const examView = document.getElementById('speakingViewExam');
  if (examView && !examView.classList.contains('is-active')) return true;
  return false;
}

function isStageActive() {
  if (!mounted || !container || !renderer || !scene || !camera) return false;
  if (contextLost) return false;
  if (lightboxOpen) return false;
  if (typeof document !== 'undefined' && document.hidden) return false;
  if (container.hidden || !container.isConnected) return false;
  if (!containerVisible) return false;
  if (isSpeakingOverlayClosed()) return false;
  const rect = container.getBoundingClientRect();
  return rect.width > 1 && rect.height > 1;
}

function syncCanvasTouchAction(active) {
  if (!renderer || !renderer.domElement) return;
  renderer.domElement.style.touchAction = active ? 'none' : '';
}

function sampleSpeakingAmplitude(dt) {
  const analyser = state.speakingAnalyser;
  if (!state.speakingRole || !analyser || !speakingData) {
    silentSec = 0;
    return 0;
  }
  try {
    analyser.getByteFrequencyData(speakingData);
  } catch (e) {
    return 0;
  }
  const len = speakingData.length;
  if (!len) return 0;
  const sampleRate = analyser.context && analyser.context.sampleRate ? analyser.context.sampleRate : 48000;
  const binHz = (sampleRate * 0.5) / len;
  const minBin = Math.max(0, Math.floor(80 / binHz));
  const maxBin = Math.min(len - 1, Math.ceil(4000 / binHz));
  let sumSq = 0;
  let count = 0;
  for (let b = minBin; b <= maxBin; b++) {
    const v = speakingData[b];
    sumSq += v * v;
    count++;
  }
  const rms = count > 0 ? Math.sqrt(sumSq / count) : 0;
  if (rms < SILENCE_FLOOR) {
    silentSec += dt;
  } else {
    silentSec = 0;
  }
  if (silentSec > SILENCE_TIMEOUT_S) return 0;
  return clamp((rms / 255) * 3.2, 0, 1);
}

function resolveGazeTarget(name, focusRole, outVec) {
  if (name === 'examiner') {
    if (focusRole === 'partner' && avatarMap.partner && avatarMap.partner.userData) {
      avatarMap.partner.userData.head.getWorldPosition(outVec);
      outVec.y += 0.12;
      return true;
    }
    outVec.copy(camera.position);
    return true;
  }
  if (name === 'partner') {
    if (focusRole === 'partner' || focusRole === 'you') {
      outVec.copy(camera.position);
      return true;
    }
    if (avatarMap.examiner && avatarMap.examiner.userData) {
      avatarMap.examiner.userData.head.getWorldPosition(outVec);
      outVec.y += 0.12;
      return true;
    }
    outVec.copy(camera.position);
    return true;
  }
  return false;
}

function getMaxAnisotropy() {
  if (!renderer || !renderer.capabilities || typeof renderer.capabilities.getMaxAnisotropy !== 'function') {
    return 1;
  }
  const maxAniso = renderer.capabilities.getMaxAnisotropy() || 1;
  // Cap anisotropy further on mobile tier (no canvas downscale allowed)
  return Math.min(lastMobile ? 2 : 4, maxAniso);
}

function getActiveMaterialUrls() {
  const active = new Set();
  if (Array.isArray(state.images) && state.images.length >= 2) {
    if (state.images[0]) active.add(state.images[0]);
    if (state.images[1]) active.add(state.images[1]);
  }
  if (state.card) active.add(state.card);
  return active;
}

function evictTextureCacheIfNeeded() {
  if (textureCache.size < MAX_CACHED_TEXTURES) return;
  const active = getActiveMaterialUrls();
  let oldestUrl = null;
  let oldestTs = Infinity;
  textureCache.forEach((entry, url) => {
    if (!active.has(url) && entry.lastUsed < oldestTs) {
      oldestTs = entry.lastUsed;
      oldestUrl = url;
    }
  });
  if (oldestUrl !== null) {
    const victim = textureCache.get(oldestUrl);
    textureCache.delete(oldestUrl);
    if (victim && victim.texture && typeof victim.texture.dispose === 'function') {
      try { victim.texture.dispose(); } catch (e) {}
    }
  }
}

function fitFaceAspect(faceMesh, boxW, boxH, imgW, imgH) {
  if (!faceMesh) return;
  if (!imgW || !imgH) {
    faceMesh.scale.set(1, 1, 1);
    return;
  }
  const imgAspect = imgW / imgH;
  const boxAspect = boxW / boxH;
  if (imgAspect > boxAspect) {
    faceMesh.scale.set(1, Math.max(0.35, boxAspect / imgAspect), 1);
  } else {
    faceMesh.scale.set(Math.max(0.35, imgAspect / boxAspect), 1, 1);
  }
}

function applyTextureToSlot(kind, slotIdx, url, entry) {
  if (!tableProps) return;
  if (kind === 'photo') {
    const slot = tableProps.photos[slotIdx];
    if (!slot) return;
    if (slot.face.userData.materialUrl !== url) return;
    if (entry && entry.status === 'ready' && entry.texture) {
      entry.texture.anisotropy = getMaxAnisotropy();
      slot.faceMat.map = entry.texture;
      slot.faceMat.color.setHex(0xffffff);
      slot.faceMat.needsUpdate = true;
      fitFaceAspect(slot.face, PHOTO_BASE_W, PHOTO_BASE_H, entry.width, entry.height);
    } else {
      slot.faceMat.map = null;
      slot.faceMat.color.setHex(PLACEHOLDER_GREY);
      slot.faceMat.needsUpdate = true;
      slot.face.scale.set(1, 1, 1);
    }
  } else if (kind === 'card') {
    if (tableProps.cardFace.userData.materialUrl !== url) return;
    if (entry && entry.status === 'ready' && entry.texture) {
      entry.texture.anisotropy = getMaxAnisotropy();
      tableProps.cardFaceMat.map = entry.texture;
      tableProps.cardFaceMat.color.setHex(0xffffff);
      tableProps.cardFaceMat.needsUpdate = true;
      fitFaceAspect(tableProps.cardFace, CARD_BASE_W, CARD_BASE_H, entry.width, entry.height);
    } else {
      tableProps.cardFaceMat.map = null;
      tableProps.cardFaceMat.color.setHex(PLACEHOLDER_GREY);
      tableProps.cardFaceMat.needsUpdate = true;
      tableProps.cardFace.scale.set(1, 1, 1);
    }
  }
}

function requestMaterialTexture(url, kind, slotIdx) {
  if (!mounted || !url || typeof url !== 'string') return;
  const now = performance.now();
  const existing = textureCache.get(url);
  if (existing) {
    existing.lastUsed = now;
    applyTextureToSlot(kind, slotIdx, url, existing);
    return;
  }

  // Show neutral grey placeholder while texture loads
  applyTextureToSlot(kind, slotIdx, url, null);
  if (!textureLoader) {
    textureLoader = new THREE.TextureLoader();
  }
  evictTextureCacheIfNeeded();

  const entry = {
    texture: null,
    status: 'loading',
    width: 0,
    height: 0,
    bytes: 0,
    lastUsed: now
  };
  textureCache.set(url, entry);

  const tex = textureLoader.load(
    url,
    loaded => {
      if (!mounted || textureCache.get(url) !== entry) {
        try { loaded.dispose(); } catch (e) {}
        return;
      }
      loaded.colorSpace = THREE.SRGBColorSpace;
      loaded.anisotropy = getMaxAnisotropy();
      loaded.generateMipmaps = true;
      loaded.minFilter = THREE.LinearMipmapLinearFilter;
      loaded.magFilter = THREE.LinearFilter;
      loaded.needsUpdate = true;
      const img = loaded.image;
      const w = img ? (img.naturalWidth || img.width || 0) : 0;
      const h = img ? (img.naturalHeight || img.height || 0) : 0;
      entry.texture = loaded;
      entry.status = 'ready';
      entry.width = w;
      entry.height = h;
      entry.bytes = w * h * 4;
      entry.lastUsed = performance.now();
      applyTextureToSlot('photo', 0, url, entry);
      applyTextureToSlot('photo', 1, url, entry);
      applyTextureToSlot('card', 0, url, entry);
      if (mounted && !lightboxOpen) {
        renderOnce(0);
        syncLoop();
      }
    },
    undefined,
    () => {
      if (textureCache.get(url) !== entry) return;
      entry.status = 'error';
      if (entry.texture) {
        try { entry.texture.dispose(); } catch (e) {}
        entry.texture = null;
      }
    }
  );
  entry.texture = tex;
}

function getPhotoAlt(index) {
  if (typeof document !== 'undefined') {
    const el = document.getElementById(index === 0 ? 'speakingPhoto1' : 'speakingPhoto2');
    if (el && el.alt) return el.alt;
  }
  return 'Photograph ' + (index + 1);
}

function getCardAlt() {
  if (typeof document !== 'undefined') {
    const el = document.getElementById('speakingCardImg');
    if (el && el.alt) return el.alt;
  }
  return 'Part 3 task card';
}

function openLightbox(url, alt) {
  if (!url || typeof document === 'undefined') return;
  const lb = document.getElementById('speaking3dLightbox');
  const img = document.getElementById('speaking3dLightboxImg');
  const closeBtn = document.getElementById('speaking3dLightboxClose');
  const titleEl = document.getElementById('speaking3dLightboxTitle');
  if (!lb || !img) return;
  img.src = url;
  img.alt = alt || '';
  if (titleEl) titleEl.textContent = alt || '';
  lb.hidden = false;
  lightboxOpen = true;
  stopLoop();
  syncCanvasTouchAction(false);
  if (closeBtn && typeof closeBtn.focus === 'function') {
    try { closeBtn.focus({ preventScroll: true }); } catch (e) { closeBtn.focus(); }
  }
}

function closeLightbox(restoreFocus) {
  if (typeof document === 'undefined') {
    lightboxOpen = false;
    return;
  }
  const lb = document.getElementById('speaking3dLightbox');
  const img = document.getElementById('speaking3dLightboxImg');
  const wasOpen = lightboxOpen || Boolean(lb && !lb.hidden);
  lightboxOpen = false;
  if (lb) lb.hidden = true;
  if (img) img.removeAttribute('src');
  if (wasOpen && restoreFocus !== false && renderer && renderer.domElement) {
    try {
      renderer.domElement.focus({ preventScroll: true });
    } catch (e) {
      try { renderer.domElement.focus(); } catch (_e) {}
    }
  }
  if (mounted) syncLoop();
}

function bindLightboxEvents() {
  if (lightboxBound || typeof document === 'undefined') return;
  const lb = document.getElementById('speaking3dLightbox');
  const closeBtn = document.getElementById('speaking3dLightboxClose');
  lbCloseListener = () => closeLightbox(true);
  lbBackdropListener = ev => {
    if (ev.target === lb) closeLightbox(true);
  };
  lbKeyListener = ev => {
    if (lightboxOpen && ev.key === 'Escape') {
      ev.preventDefault();
      ev.stopPropagation();
      closeLightbox(true);
    }
  };
  if (closeBtn) closeBtn.addEventListener('click', lbCloseListener);
  if (lb) lb.addEventListener('click', lbBackdropListener);
  document.addEventListener('keydown', lbKeyListener, true);
  lightboxBound = true;
}

function unbindLightboxEvents() {
  if (!lightboxBound || typeof document === 'undefined') return;
  const lb = document.getElementById('speaking3dLightbox');
  const closeBtn = document.getElementById('speaking3dLightboxClose');
  if (closeBtn && lbCloseListener) closeBtn.removeEventListener('click', lbCloseListener);
  if (lb && lbBackdropListener) lb.removeEventListener('click', lbBackdropListener);
  if (lbKeyListener) document.removeEventListener('keydown', lbKeyListener, true);
  lbCloseListener = null;
  lbBackdropListener = null;
  lbKeyListener = null;
  lightboxBound = false;
}

function syncThumbs() {
  if (!mounted || !container || typeof document === 'undefined') return;
  const mobile = isMobileViewport();
  const items = [];
  if (Array.isArray(state.images) && state.images.length >= 2) {
    if (state.images[0]) items.push({ url: state.images[0], alt: getPhotoAlt(0) });
    if (state.images[1]) items.push({ url: state.images[1], alt: getPhotoAlt(1) });
  } else if (state.card) {
    items.push({ url: state.card, alt: getCardAlt() });
  }
  const show = Boolean(mobile && items.length > 0);
  const changed = show !== thumbsVisible;
  thumbsVisible = show;

  const examView = document.getElementById('speakingViewExam');
  if (examView) examView.classList.toggle('has-thumbs', show);
  container.classList.toggle('has-thumbs', show);

  if (!thumbsEl) return;
  if (!show) {
    thumbsEl.hidden = true;
    thumbsEl.innerHTML = '';
  } else {
    thumbsEl.innerHTML = '';
    items.forEach(item => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'spk3d-thumb-btn';
      btn.setAttribute('aria-label', item.alt || 'Enlarge');
      const im = document.createElement('img');
      im.src = item.url;
      im.alt = item.alt || '';
      btn.appendChild(im);
      btn.addEventListener('click', ev => {
        ev.stopPropagation();
        openLightbox(item.url, item.alt);
      });
      thumbsEl.appendChild(btn);
    });
    thumbsEl.hidden = false;
  }
  if (changed) updateSize();
}

function applyMaterialLiftOffset() {
  if (!tableProps) return;
  const dist = matLiftProgress * REDUCED_LIFT_M;
  for (let i = 0; i < tableProps.photos.length; i++) {
    const p = tableProps.photos[i];
    p.group.position.copy(p.basePos).addScaledVector(LIFT_DIR, dist);
  }
  tableProps.cardGroup.position.copy(tableProps.cardBasePos).addScaledVector(LIFT_DIR, dist);
}

function updateMaterialLift(nowMs) {
  if (!matLiftActive) return true;
  const now = typeof nowMs === 'number' ? nowMs : performance.now();
  const u = clamp((now - matLiftStartMs) / REDUCED_LIFT_MS, 0, 1);
  const ease = easeInOutCubic(u);
  matLiftProgress = matLiftFrom + (matLiftTo - matLiftFrom) * ease;
  applyMaterialLiftOffset();
  if (u >= 1) {
    matLiftProgress = matLiftTo;
    matLiftActive = false;
    applyMaterialLiftOffset();
    return true;
  }
  return false;
}

function advanceDolly(nowMs) {
  if (dollyPhase === 'idle') return true;
  const now = typeof nowMs === 'number' ? nowMs : performance.now();
  const elapsed = Math.max(0, now - dollyStartMs);
  if (dollyPhase === 'waiting') {
    if (elapsed < dollyWaitMs) return false;
    dollyPhase = 'moving';
    dollyStartMs = dollyStartMs + dollyWaitMs;
  }
  const moveElapsed = Math.max(0, now - dollyStartMs);
  const u = dollyDurMs > 0 ? clamp(moveElapsed / dollyDurMs, 0, 1) : 1;
  const ease = easeInOutCubic(u);
  camPos.lerpVectors(dollyFromPos, dollyToPos, ease);
  camTarget.lerpVectors(dollyFromTarget, dollyToTarget, ease);
  camFov = dollyFromFov + (dollyToFov - dollyFromFov) * ease;
  dollyWeight = dollyFromWeight + (dollyToWeight - dollyFromWeight) * ease;
  if (dollyGoal === 'base' && !lookDragging) {
    // Restore base yaw/pitch cleanly as the dolly returns
    lookYaw = clamp(dollyReturnLookYaw * (1 - ease), LOOK_YAW_MIN, LOOK_YAW_MAX);
    lookPitch = clamp(dollyReturnLookPitch * (1 - ease), LOOK_PITCH_MIN, LOOK_PITCH_MAX);
  }
  if (u >= 1) {
    camPos.copy(dollyToPos);
    camTarget.copy(dollyToTarget);
    camFov = dollyToFov;
    dollyWeight = dollyToWeight;
    dollyPhase = 'idle';
    if (dollyGoal === 'base' && !lookDragging) {
      lookYaw = 0;
      lookPitch = 0;
      lookVelYaw = 0;
      lookVelPitch = 0;
      lookReturning = false;
      lookIdleStartMs = 0;
    }
    return true;
  }
  return false;
}

function requestDolly(goal) {
  const now = performance.now();
  advanceDolly(now);
  updateMaterialLift(now);

  if (isReducedMotion()) {
    // Reduced motion skips the camera dolly and lifts the material 0.10 m toward the camera
    dollyGoal = 'base';
    dollyPhase = 'idle';
    camPos.copy(CAM_POSES.base.pos);
    camTarget.copy(CAM_POSES.base.target);
    camFov = CAM_POSES.base.fov;
    dollyWeight = 0;
    const targetLift = goal === 'base' ? 0 : 1;
    if (Math.abs(matLiftProgress - targetLift) > 0.001 || (matLiftActive && matLiftTo !== targetLift)) {
      matLiftFrom = matLiftProgress;
      matLiftTo = targetLift;
      matLiftStartMs = now;
      matLiftActive = true;
    }
    if (mounted) {
      renderOnce(0);
      syncLoop();
    }
    return;
  }

  // Normal motion: keep material seated on the desk pad and run camera dolly
  if (matLiftProgress !== 0 || matLiftActive) {
    matLiftProgress = 0;
    matLiftFrom = 0;
    matLiftTo = 0;
    matLiftActive = false;
    applyMaterialLiftOffset();
  }

  const targetPose = CAM_POSES[goal] || CAM_POSES.base;
  if (goal === dollyGoal) {
    if (dollyPhase !== 'idle') return;
    if (
      camPos.distanceToSquared(targetPose.pos) < 1e-6 &&
      camTarget.distanceToSquared(targetPose.target) < 1e-6 &&
      Math.abs(camFov - targetPose.fov) < 0.01
    ) {
      return;
    }
  }

  // Retarget seamlessly from the current interpolated pose (no queue, no snap)
  dollyFromPos.copy(camPos);
  dollyFromTarget.copy(camTarget);
  dollyFromFov = camFov;
  dollyFromWeight = dollyWeight;
  dollyToPos.copy(targetPose.pos);
  dollyToTarget.copy(targetPose.target);
  dollyToFov = targetPose.fov;
  dollyToWeight = goal === 'base' ? 0 : 1;
  dollyGoal = goal;
  dollyStartMs = now;

  if (goal === 'base') {
    dollyWaitMs = 0;
    dollyDurMs = DOLLY_RETURN_MS;
    dollyPhase = 'moving';
    dollyReturnLookYaw = lookYaw;
    dollyReturnLookPitch = lookPitch;
  } else {
    dollyWaitMs = DOLLY_WAIT_MS;
    dollyDurMs = DOLLY_EASE_MS;
    dollyPhase = 'waiting';
  }

  if (mounted && !rafId) syncLoop();
}

function resetCameraAndDolly() {
  camPos.copy(CAM_POSES.base.pos);
  camTarget.copy(CAM_POSES.base.target);
  camFov = CAM_POSES.base.fov;
  dollyGoal = 'base';
  dollyPhase = 'idle';
  dollyStartMs = 0;
  dollyWaitMs = 0;
  dollyDurMs = 0;
  dollyFromPos.copy(CAM_POSES.base.pos);
  dollyFromTarget.copy(CAM_POSES.base.target);
  dollyFromFov = CAM_POSES.base.fov;
  dollyFromWeight = 0;
  dollyToPos.copy(CAM_POSES.base.pos);
  dollyToTarget.copy(CAM_POSES.base.target);
  dollyToFov = CAM_POSES.base.fov;
  dollyToWeight = 0;
  dollyWeight = 0;
  dollyReturnLookYaw = 0;
  dollyReturnLookPitch = 0;
  matLiftProgress = 0;
  matLiftFrom = 0;
  matLiftTo = 0;
  matLiftStartMs = 0;
  matLiftActive = false;
}

function updateLook(dt, nowMs) {
  if (!camera) return true;
  const now = typeof nowMs === 'number' ? nowMs : performance.now();
  const dollySettled = advanceDolly(now);
  const hasMaterial = Boolean(state.images || state.card);
  const displaced = Math.abs(lookYaw) > 0.0005 || Math.abs(lookPitch) > 0.0005;

  if (!lookDragging && dollyPhase === 'idle') {
    const moving = Math.abs(lookVelYaw) >= LOOK_INERTIA_STOP || Math.abs(lookVelPitch) >= LOOK_INERTIA_STOP;
    if (moving && dt > 0) {
      const frames = dt * 60;
      const decay = Math.pow(LOOK_INERTIA_DECAY, frames);
      lookYaw = clamp(lookYaw + lookVelYaw * frames, LOOK_YAW_MIN, LOOK_YAW_MAX);
      lookPitch = clamp(lookPitch + lookVelPitch * frames, LOOK_PITCH_MIN, LOOK_PITCH_MAX);
      lookVelYaw *= decay;
      lookVelPitch *= decay;
      if (Math.abs(lookVelYaw) < LOOK_INERTIA_STOP) lookVelYaw = 0;
      if (Math.abs(lookVelPitch) < LOOK_INERTIA_STOP) lookVelPitch = 0;
    } else if (!moving && lookReturning) {
      if (hasMaterial) {
        lookReturning = false;
      } else {
        const elapsed = Math.max(0, (now - lookReturnStartMs) * 0.001);
        const u = clamp(elapsed / LOOK_RETURN_DUR_S, 0, 1);
        const ease = 1 - Math.pow(1 - u, 3);
        lookYaw = clamp(lookReturnStartYaw * (1 - ease), LOOK_YAW_MIN, LOOK_YAW_MAX);
        lookPitch = clamp(lookReturnStartPitch * (1 - ease), LOOK_PITCH_MIN, LOOK_PITCH_MAX);
        if (u >= 1) {
          lookYaw = 0;
          lookPitch = 0;
          lookReturning = false;
          lookIdleStartMs = 0;
        }
      }
    } else if (!moving && displaced && !hasMaterial) {
      if (!lookIdleStartMs) lookIdleStartMs = now;
      if ((now - lookIdleStartMs) * 0.001 >= LOOK_IDLE_RETURN_S) {
        lookReturning = true;
        lookReturnStartYaw = clamp(lookYaw, LOOK_YAW_MIN, LOOK_YAW_MAX);
        lookReturnStartPitch = clamp(lookPitch, LOOK_PITCH_MIN, LOOK_PITCH_MAX);
        lookReturnStartMs = now;
      }
    } else if (!displaced) {
      lookIdleStartMs = 0;
    }
  }

  camera.position.copy(camPos);
  if (Math.abs(camera.fov - camFov) > 0.001) {
    camera.fov = camFov;
    camera.updateProjectionMatrix();
  }

  // Dolly target wins during dolly while look-around offsets remain preserved in state.
  // Negative lookYaw turns the camera left toward the partner; positive turns right.
  _vCamDir.subVectors(camTarget, camPos).normalize();
  const baseYaw = Math.atan2(-_vCamDir.x, -_vCamDir.z);
  const basePitch = Math.asin(clamp(_vCamDir.y, -1, 1));
  const lookBlend = 1 - dollyWeight;
  camera.rotation.order = 'YXZ';
  camera.rotation.set(basePitch + lookPitch * lookBlend, baseYaw - lookYaw * lookBlend, 0);

  const stillDisplaced = Math.abs(lookYaw) > 0.0005 || Math.abs(lookPitch) > 0.0005;
  const stillMoving = Math.abs(lookVelYaw) >= LOOK_INERTIA_STOP || Math.abs(lookVelPitch) >= LOOK_INERTIA_STOP;
  return dollySettled && !lookDragging && !lookReturning && !stillMoving && (hasMaterial || !stillDisplaced);
}

function updateAvatars(dt, elapsedSec) {
  const calm = isReducedMotion();
  const focusRole = state.speakingRole || state.activeRole;
  const ampTarget = sampleSpeakingAmplitude(dt);
  let settled = true;

  for (let i = 0; i < avatars.length; i++) {
    const ud = avatars[i].userData;
    if (!ud || !ud.torso || !ud.head) continue;

    // 1. Subtle breathing (disabled in reduced motion)
    if (calm) {
      ud.torso.scale.y = 1;
    } else {
      ud.torso.scale.y = 1 + BREATH_AMP * Math.sin(2 * Math.PI * BREATH_HZ * elapsedSec + ud.phaseOffset);
    }

    // 2. Head gaze + spring easing
    let targetYaw = 0;
    let targetPitch = 0;
    let targetRoll = 0;
    let targetEyeYaw = 0;
    let targetEyePitch = 0;

    if (ud.name === 'assessor') {
      // Assessor is independent of setActiveRole: head-down writing with a brief glance every ~9 s
      if (calm) {
        targetYaw = ASSESSOR_YAW_BASE;
        targetPitch = ASSESSOR_PITCH_DOWN;
      } else {
        const cycle = elapsedSec % ASSESSOR_CYCLE_S;
        const glance = cycle >= (ASSESSOR_CYCLE_S - ASSESSOR_GLANCE_S);
        const basePitch = glance ? ASSESSOR_PITCH_GLANCE : ASSESSOR_PITCH_DOWN;
        const writeOsc = 0.006 * Math.sin(2 * Math.PI * 0.9 * elapsedSec);
        targetPitch = basePitch + writeOsc;
        targetYaw = ASSESSOR_YAW_BASE + 0.004 * Math.sin(2 * Math.PI * 0.9 * elapsedSec + 1.1);
      }
      targetRoll = 0;
    } else if (camera && resolveGazeTarget(ud.name, focusRole, _vTargetWorld)) {
      ud.head.getWorldPosition(_vHeadWorld);
      _vHeadWorld.y += 0.12;
      _vLocal.subVectors(_vTargetWorld, _vHeadWorld);
      ud.torso.getWorldQuaternion(_qInvTorso).invert();
      _vLocal.applyQuaternion(_qInvTorso);

      const rawYaw = Math.atan2(-_vLocal.x, -_vLocal.z);
      const horiz = Math.hypot(_vLocal.x, _vLocal.z) || 1e-4;
      const rawPitch = Math.atan2(_vLocal.y, horiz);
      const yawLim = ud.name === 'partner' ? MAX_YAW_PARTNER : MAX_YAW;

      if (calm) {
        targetYaw = clamp(rawYaw, -MAX_YAW_REDUCED, MAX_YAW_REDUCED);
        targetPitch = 0;
        targetRoll = 0;
      } else {
        targetYaw = clamp(rawYaw, -yawLim, yawLim);
        targetPitch = clamp(rawPitch, -MAX_PITCH, MAX_PITCH);
        targetRoll = 0;
        if (focusRole === ud.name) {
          targetYaw = clamp(
            targetYaw + 0.05 * Math.sin(2 * Math.PI * 0.35 * elapsedSec + ud.phaseOffset),
            -yawLim,
            yawLim
          );
          targetPitch = clamp(
            targetPitch + 0.02 * Math.sin(2 * Math.PI * 0.22 * elapsedSec + ud.phaseOffset),
            -MAX_PITCH,
            MAX_PITCH
          );
          targetRoll = clamp(
            0.015 * Math.sin(2 * Math.PI * 0.19 * elapsedSec + ud.phaseOffset),
            -MAX_ROLL,
            MAX_ROLL
          );
        }
      }

      // Subtle eye lead/counter-rotation toward the gaze target
      targetEyeYaw = clamp(rawYaw - ud.yaw, -MAX_EYE_YAW, MAX_EYE_YAW);
      targetEyePitch = calm ? 0 : clamp(rawPitch - ud.pitch, -MAX_EYE_PITCH, MAX_EYE_PITCH);
    }

    if (dt > 0) {
      ud.yawVel += ((targetYaw - ud.yaw) * SPRING_K - ud.yawVel * SPRING_D) * dt;
      ud.yaw += ud.yawVel * dt;
      ud.pitchVel += ((targetPitch - ud.pitch) * SPRING_K - ud.pitchVel * SPRING_D) * dt;
      ud.pitch += ud.pitchVel * dt;
      ud.rollVel += ((targetRoll - ud.roll) * SPRING_K - ud.rollVel * SPRING_D) * dt;
      ud.roll += ud.rollVel * dt;

      const eyeLerp = 1 - Math.exp(-dt * 14);
      ud.eyeYaw += (targetEyeYaw - ud.eyeYaw) * eyeLerp;
      ud.eyePitch += (targetEyePitch - ud.eyePitch) * eyeLerp;
    }

    ud.head.rotation.set(ud.pitch, ud.yaw, ud.roll);
    if (ud.eyes) {
      ud.eyes.rotation.set(ud.eyePitch, ud.eyeYaw, 0);
    }

    if (
      Math.abs(targetYaw - ud.yaw) > 0.003 ||
      Math.abs(ud.yawVel) > 0.005 ||
      Math.abs(targetPitch - ud.pitch) > 0.003 ||
      Math.abs(ud.pitchVel) > 0.005
    ) {
      settled = false;
    }

    // 3. Amplitude mouth-sync (assessor stays silent)
    if (ud.mouth) {
      const targetOpen = ud.name === state.speakingRole && ud.name !== 'assessor' ? ampTarget : 0;
      if (dt > 0) {
        const tau = targetOpen > ud.mouthOpen ? MOUTH_ATTACK_S : MOUTH_RELEASE_S;
        ud.mouthOpen += (targetOpen - ud.mouthOpen) * Math.min(1, dt / tau);
        if (ud.mouthOpen < 0.001 && targetOpen === 0) ud.mouthOpen = 0;
      }
      ud.mouth.scale.y = MOUTH_BASE_SCALE + ud.mouthOpen * MOUTH_SCALE_GAIN;
      ud.mouth.position.y = ud.mouthBaseY - ud.mouthOpen * MOUTH_DROP_Y;
      if (ud.jaw) {
        ud.jaw.rotation.x = -ud.mouthOpen * 0.14;
      }
      if (ud.mouthOpen > 0.001 || targetOpen > 0) {
        settled = false;
      }
    }
  }

  return settled;
}

function renderOnce(dtOverride) {
  if (!mounted || !renderer || !scene || !camera || contextLost) return true;
  const now = performance.now();
  const totalDt = typeof dtOverride === 'number'
    ? dtOverride
    : Math.min(Math.max(0, (now - lastFrameMs) * 0.001), 0.5);
  lastFrameMs = now;
  const elapsed = (now - clockStart) * 0.001;
  let settled = true;
  let lookSettled = true;
  const liftSettled = updateMaterialLift(now);
  if (totalDt <= 0) {
    settled = updateAvatars(0, elapsed);
    lookSettled = updateLook(0, now);
  } else {
    let rem = totalDt;
    while (rem > 0) {
      const step = Math.min(rem, MAX_DT);
      rem -= step;
      settled = updateAvatars(step, elapsed - rem);
      lookSettled = updateLook(step, now);
    }
  }
  const r0 = performance.now();
  renderer.render(scene, camera);
  const rMs = performance.now() - r0;
  renderTimes[renderTimeIdx] = rMs;
  renderTimeIdx = (renderTimeIdx + 1) % renderTimes.length;
  if (renderTimeCount < renderTimes.length) renderTimeCount++;
  return settled && lookSettled && liftSettled;
}

function stopLoop() {
  if (rafId) {
    cancelAnimationFrame(rafId);
    rafId = 0;
  }
}

function shouldKeepAnimating(settled) {
  if (!isReducedMotion()) return true;
  if (state.speakingRole && state.speakingAnalyser) return true;
  return !settled;
}

function tick() {
  rafId = 0;
  const active = isStageActive();
  syncCanvasTouchAction(active);
  if (!active) return;
  const settled = renderOnce();
  if (shouldKeepAnimating(settled)) {
    rafId = requestAnimationFrame(tick);
  }
}

function syncLoop() {
  const active = isStageActive();
  syncCanvasTouchAction(active);
  if (!active) {
    stopLoop();
    return;
  }
  lastFrameMs = performance.now();
  const settled = renderOnce(0);
  if (!shouldKeepAnimating(settled)) {
    stopLoop();
  } else if (!rafId) {
    rafId = requestAnimationFrame(tick);
  }
}

function updateSize() {
  if (!mounted || !container || !renderer || !camera) return;
  const rect = container.getBoundingClientRect();
  const w = Math.floor(rect.width);
  const fullH = Math.floor(rect.height);
  const h = Math.max(0, fullH - (thumbsVisible ? 64 : 0));
  if (w < 2 || h < 2) {
    syncCanvasTouchAction(false);
    stopLoop();
    return;
  }
  const mobile = isMobileViewport();
  if (mobile !== lastMobile) {
    lastMobile = mobile;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, mobile ? 1.5 : 2));
    if (keyLight) {
      keyLight.castShadow = !mobile;
      renderer.shadowMap.enabled = !mobile;
    }
    const maxAniso = getMaxAnisotropy();
    textureCache.forEach(entry => {
      if (entry.texture) {
        entry.texture.anisotropy = maxAniso;
        entry.texture.needsUpdate = true;
      }
    });
    syncThumbs();
  }
  const canvas = renderer.domElement;
  if (canvas) {
    canvas.style.bottom = thumbsVisible ? '64px' : '0';
    canvas.style.height = thumbsVisible ? 'calc(100% - 64px)' : '100%';
  }
  camera.fov = camFov;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h, false);
  syncLoop();
}

function onPointerDown(ev) {
  if (!mounted || !renderer || !renderer.domElement) return;
  if (ev.button && ev.button !== 0) return;
  // Single-pointer look only; ignore second finger (no zoom, no pinch)
  if (lookPointerId !== null) {
    lookDragging = false;
    lookPointerId = null;
    lookVelYaw = 0;
    lookVelPitch = 0;
    return;
  }
  lookPointerId = ev.pointerId;
  lookDragging = true;
  lookReturning = false;
  lookVelYaw = 0;
  lookVelPitch = 0;
  lookIdleStartMs = 0;
  lookStartX = ev.clientX;
  lookStartY = ev.clientY;
  lookLastX = ev.clientX;
  lookLastY = ev.clientY;
  lookLastMoveMs = performance.now();
  lookDragDist = 0;
  renderer.domElement.dataset.wasDrag = '0';
  try {
    renderer.domElement.setPointerCapture(ev.pointerId);
  } catch (e) {}
  if (!rafId) syncLoop();
}

function onPointerMove(ev) {
  if (!lookDragging || ev.pointerId !== lookPointerId) return;
  const dx = ev.clientX - lookLastX;
  const dy = ev.clientY - lookLastY;
  lookLastX = ev.clientX;
  lookLastY = ev.clientY;
  lookLastMoveMs = performance.now();

  const dist = Math.hypot(ev.clientX - lookStartX, ev.clientY - lookStartY);
  if (dist > lookDragDist) lookDragDist = dist;
  if (lookDragDist > LOOK_DRAG_TAP_PX && renderer && renderer.domElement) {
    renderer.domElement.dataset.wasDrag = '1';
  }

  const dyaw = dx * LOOK_SENS;
  const dpitch = dy * LOOK_SENS;
  lookYaw = clamp(lookYaw + dyaw, LOOK_YAW_MIN, LOOK_YAW_MAX);
  lookPitch = clamp(lookPitch + dpitch, LOOK_PITCH_MIN, LOOK_PITCH_MAX);
  lookVelYaw = lookVelYaw * 0.5 + clamp(dyaw, -0.005, 0.005) * 0.5;
  lookVelPitch = lookVelPitch * 0.5 + clamp(dpitch, -0.005, 0.005) * 0.5;

  updateLook(0);
}

function tryRaycastMaterialTap(ev) {
  if (!mounted || !renderer || !renderer.domElement || !camera || !tableProps || lightboxOpen) return false;
  const rect = renderer.domElement.getBoundingClientRect();
  if (rect.width <= 1 || rect.height <= 1) return false;
  _pointerNdc.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
  _pointerNdc.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
  camera.updateMatrixWorld(true);
  _raycaster.setFromCamera(_pointerNdc, camera);
  const targets = [];
  if (tableProps.photoGroup && tableProps.photoGroup.visible) {
    for (let i = 0; i < tableProps.photos.length; i++) {
      targets.push(tableProps.photos[i].face, tableProps.photos[i].backing);
    }
  }
  if (tableProps.cardGroup && tableProps.cardGroup.visible) {
    targets.push(tableProps.cardFace, tableProps.cardBacking);
  }
  if (!targets.length) return false;
  const hits = _raycaster.intersectObjects(targets, false);
  if (hits.length > 0) {
    const ud = hits[0].object && hits[0].object.userData;
    if (ud && ud.materialUrl) {
      openLightbox(ud.materialUrl, ud.materialAlt || '');
      return true;
    }
  }
  return false;
}

function finishPointerDrag(ev) {
  if (ev.pointerId !== lookPointerId) return;
  if (renderer && renderer.domElement) {
    try {
      renderer.domElement.releasePointerCapture(ev.pointerId);
    } catch (e) {}
  }
  if (performance.now() - lookLastMoveMs > 60) {
    lookVelYaw = 0;
    lookVelPitch = 0;
  }
  const wasTap = ev.type === 'pointerup' && lookDragDist < LOOK_DRAG_TAP_PX;
  if (lookDragDist > LOOK_DRAG_TAP_PX) {
    suppressClickUntil = performance.now() + 300;
  }
  lookDragging = false;
  lookPointerId = null;
  lookIdleStartMs = performance.now();
  if (wasTap && tryRaycastMaterialTap(ev)) {
    return;
  }
  if (!rafId) syncLoop();
}

function onCanvasClickCapture(ev) {
  // A drag > 10 px must never trigger a tap/click (future lightbox relies on this)
  if (performance.now() < suppressClickUntil) {
    ev.preventDefault();
    ev.stopPropagation();
  }
}

function resetLookState() {
  lookYaw = 0;
  lookPitch = 0;
  lookVelYaw = 0;
  lookVelPitch = 0;
  lookDragging = false;
  lookReturning = false;
  lookPointerId = null;
  lookStartX = 0;
  lookStartY = 0;
  lookLastX = 0;
  lookLastY = 0;
  lookLastMoveMs = 0;
  lookDragDist = 0;
  lookIdleStartMs = 0;
  lookReturnStartYaw = 0;
  lookReturnStartPitch = 0;
  lookReturnStartMs = 0;
  suppressClickUntil = 0;
}

function onVisibilityChange() {
  syncLoop();
}

function onWindowResize() {
  updateSize();
}

function onContextLost(ev) {
  ev.preventDefault();
  contextLost = true;
  syncCanvasTouchAction(false);
  stopLoop();
}

function onContextRestored() {
  contextLost = false;
  syncLoop();
}

function disposeScene(root) {
  if (!root) return;
  const geos = new Set();
  const mats = new Set();
  root.traverse(obj => {
    if (obj.geometry) geos.add(obj.geometry);
    if (obj.material) {
      if (Array.isArray(obj.material)) {
        obj.material.forEach(m => mats.add(m));
      } else {
        mats.add(obj.material);
      }
    }
  });
  geos.forEach(g => {
    try { g.dispose(); } catch (e) {}
  });
  mats.forEach(m => {
    try {
      if (m.map && typeof m.map.dispose === 'function') m.map.dispose();
      m.dispose();
    } catch (e) {}
  });
}

function disposeTextureCache() {
  textureCache.forEach(entry => {
    if (entry && entry.texture && typeof entry.texture.dispose === 'function') {
      try { entry.texture.dispose(); } catch (e) {}
    }
  });
  textureCache.clear();
  textureLoader = null;
}

function unmount() {
  stopLoop();
  closeLightbox(false);
  unbindLightboxEvents();
  if (typeof document !== 'undefined') {
    const examView = document.getElementById('speakingViewExam');
    if (examView) examView.classList.remove('has-thumbs');
  }
  if (container) {
    container.classList.remove('has-thumbs');
  }
  if (thumbsEl && thumbsEl.parentNode) {
    thumbsEl.parentNode.removeChild(thumbsEl);
  }
  thumbsEl = null;
  thumbsVisible = false;
  if (resizeObserver) {
    try { resizeObserver.disconnect(); } catch (e) {}
    resizeObserver = null;
  }
  if (intersectionObserver) {
    try { intersectionObserver.disconnect(); } catch (e) {}
    intersectionObserver = null;
  }
  if (overlayObserver) {
    try { overlayObserver.disconnect(); } catch (e) {}
    overlayObserver = null;
  }
  if (viewObserver) {
    try { viewObserver.disconnect(); } catch (e) {}
    viewObserver = null;
  }
  if (motionMql && motionListener) {
    try {
      if (typeof motionMql.removeEventListener === 'function') {
        motionMql.removeEventListener('change', motionListener);
      } else if (typeof motionMql.removeListener === 'function') {
        motionMql.removeListener(motionListener);
      }
    } catch (e) {}
    motionMql = null;
    motionListener = null;
  }
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', onVisibilityChange);
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('resize', onWindowResize);
  }
  if (renderer && renderer.domElement) {
    const c = renderer.domElement;
    c.style.touchAction = '';
    c.removeEventListener('pointerdown', onPointerDown);
    c.removeEventListener('pointermove', onPointerMove);
    c.removeEventListener('pointerup', finishPointerDrag);
    c.removeEventListener('pointercancel', finishPointerDrag);
    c.removeEventListener('click', onCanvasClickCapture, true);
    c.removeEventListener('webglcontextlost', onContextLost);
    c.removeEventListener('webglcontextrestored', onContextRestored);
    if (c.parentNode) {
      c.parentNode.removeChild(c);
    }
  }
  if (scene) {
    disposeScene(scene);
    scene = null;
  }
  disposeTextureCache();
  tableProps = null;
  if (renderer) {
    try { renderer.dispose(); } catch (e) {}
    renderer = null;
  }
  camera = null;
  keyLight = null;
  avatars = [];
  allFigures = [];
  avatarMap = { examiner: null, partner: null, assessor: null, you: null };
  sceneSharedGeos = null;
  sceneAvatarConfigs = null;
  state.speakingRole = null;
  state.speakingAnalyser = null;
  speakingData = null;
  silentSec = 0;
  resetLookState();
  resetCameraAndDolly();
  renderTimeIdx = 0;
  renderTimeCount = 0;
  container = null;
  lastMobile = null;
  contextLost = false;
  containerVisible = true;
  mounted = false;
}

function mount(containerEl) {
  if (!containerEl || typeof containerEl.appendChild !== 'function') return false;
  if (!supported()) return false;
  if (mounted && container === containerEl) {
    updateSize();
    return true;
  }
  if (mounted) unmount();

  const mobile = isMobileViewport();
  prefersReducedMotion = detectReducedMotion();
  lastMobile = mobile;
  contextLost = false;
  containerVisible = true;
  lightboxOpen = false;
  thumbsVisible = false;
  resetLookState();
  resetCameraAndDolly();
  renderTimeIdx = 0;
  renderTimeCount = 0;

  let webglRenderer;
  try {
    webglRenderer = new THREE.WebGLRenderer({
      antialias: !mobile,
      alpha: false,
      powerPreference: 'default',
      preserveDrawingBuffer: true
    });
  } catch (e) {
    return false;
  }

  webglRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, mobile ? 1.5 : 2));
  webglRenderer.toneMapping = THREE.ACESFilmicToneMapping;
  webglRenderer.toneMappingExposure = 1.05;
  webglRenderer.outputColorSpace = THREE.SRGBColorSpace;
  webglRenderer.shadowMap.enabled = !mobile;
  if (!mobile) {
    webglRenderer.shadowMap.type = THREE.PCFSoftShadowMap;
  }

  const canvas = webglRenderer.domElement;
  canvas.style.position = 'absolute';
  canvas.style.inset = '0';
  canvas.style.width = '100%';
  canvas.style.height = '100%';
  canvas.style.display = 'block';
  canvas.setAttribute('aria-hidden', 'true');
  canvas.tabIndex = -1;

  canvas.addEventListener('pointerdown', onPointerDown);
  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('pointerup', finishPointerDrag);
  canvas.addEventListener('pointercancel', finishPointerDrag);
  canvas.addEventListener('click', onCanvasClickCapture, true);
  canvas.addEventListener('webglcontextlost', onContextLost, false);
  canvas.addEventListener('webglcontextrestored', onContextRestored, false);

  const rect = containerEl.getBoundingClientRect();
  const initW = Math.max(2, Math.floor(rect.width || containerEl.clientWidth || 320));
  const initH = Math.max(2, Math.floor(rect.height || containerEl.clientHeight || 240));

  camera = new THREE.PerspectiveCamera(FOV_BASE, initW / initH, CAM_NEAR, 25);
  camera.position.copy(CAM_BASE_POS);
  camera.rotation.order = 'YXZ';
  camera.rotation.set(CAM_BASE_PITCH, CAM_BASE_YAW, 0);

  scene = buildScene(mobile);
  scene.updateMatrixWorld(true);
  renderer = webglRenderer;
  container = containerEl;
  clockStart = performance.now();
  lastFrameMs = clockStart;
  mounted = true;

  containerEl.innerHTML = '';
  containerEl.appendChild(canvas);
  if (typeof document !== 'undefined') {
    thumbsEl = document.createElement('div');
    thumbsEl.className = 'spk3d-thumbs';
    thumbsEl.hidden = true;
    containerEl.appendChild(thumbsEl);
  }
  bindLightboxEvents();
  renderer.setSize(initW, initH, false);

  if (typeof ResizeObserver === 'function') {
    resizeObserver = new ResizeObserver(() => updateSize());
    resizeObserver.observe(containerEl);
  }
  if (typeof IntersectionObserver === 'function') {
    intersectionObserver = new IntersectionObserver(entries => {
      if (entries && entries.length) {
        containerVisible = entries[0].isIntersecting;
        syncLoop();
      }
    });
    intersectionObserver.observe(containerEl);
  }
  if (typeof MutationObserver === 'function' && typeof document !== 'undefined') {
    const ov = document.getElementById('speakingOverlay');
    if (ov) {
      overlayObserver = new MutationObserver(() => syncLoop());
      overlayObserver.observe(ov, { attributes: true, attributeFilter: ['class'] });
    }
    const examView = document.getElementById('speakingViewExam');
    if (examView) {
      viewObserver = new MutationObserver(() => syncLoop());
      viewObserver.observe(examView, { attributes: true, attributeFilter: ['class'] });
    }
  }
  if (typeof window !== 'undefined' && window.matchMedia) {
    try {
      motionMql = window.matchMedia('(prefers-reduced-motion: reduce)');
      motionListener = ev => {
        prefersReducedMotion = Boolean(ev.matches);
        syncLoop();
      };
      if (typeof motionMql.addEventListener === 'function') {
        motionMql.addEventListener('change', motionListener);
      } else if (typeof motionMql.addListener === 'function') {
        motionMql.addListener(motionListener);
      }
    } catch (e) {}
  }

  document.addEventListener('visibilitychange', onVisibilityChange);
  window.addEventListener('resize', onWindowResize);

  // Sync any pre-existing table materials if set prior to mount
  syncTableMaterialsFromState();

  // Render first frame synchronously so canvas is populated immediately
  renderOnce(0);
  syncLoop();
  return true;
}

function isMounted() {
  return mounted;
}

function setActiveRole(role) {
  const next = role === undefined ? null : role;
  if (!VALID_ROLES.has(next)) return;
  state.activeRole = next;
  if (mounted && !rafId) syncLoop();
}

function setSpeaking(role, analyser) {
  const next = role === undefined ? null : role;
  if (!VALID_ROLES.has(next)) return;
  state.speakingRole = next;
  if (
    next &&
    analyser &&
    typeof analyser === 'object' &&
    typeof analyser.getByteFrequencyData === 'function'
  ) {
    const binCount = Math.max(1, Number(analyser.frequencyBinCount) || 128);
    if (!speakingData || speakingData.length !== binCount) {
      speakingData = new Uint8Array(binCount);
    }
    state.speakingAnalyser = analyser;
    silentSec = 0;
  } else {
    state.speakingAnalyser = null;
    speakingData = null;
    silentSec = 0;
  }
  if (mounted && !rafId) syncLoop();
}

function syncTableMaterialsFromState() {
  if (!mounted || !tableProps) return;
  const hasPhotos = Array.isArray(state.images) && state.images.length >= 2 && state.images[0] && state.images[1];
  const hasCard = Boolean(state.card);

  if (hasPhotos) {
    tableProps.cardGroup.visible = false;
    tableProps.cardFace.userData.materialUrl = '';
    tableProps.cardBacking.userData.materialUrl = '';
    tableProps.photoGroup.visible = true;
    for (let i = 0; i < 2; i++) {
      const url = state.images[i];
      const alt = getPhotoAlt(i);
      const slot = tableProps.photos[i];
      slot.face.userData.materialUrl = url;
      slot.face.userData.materialAlt = alt;
      slot.backing.userData.materialUrl = url;
      slot.backing.userData.materialAlt = alt;
      requestMaterialTexture(url, 'photo', i);
    }
    syncThumbs();
    requestDolly('photos');
  } else if (hasCard) {
    tableProps.photoGroup.visible = false;
    for (let i = 0; i < 2; i++) {
      tableProps.photos[i].face.userData.materialUrl = '';
      tableProps.photos[i].backing.userData.materialUrl = '';
    }
    tableProps.cardGroup.visible = true;
    const alt = getCardAlt();
    tableProps.cardFace.userData.materialUrl = state.card;
    tableProps.cardFace.userData.materialAlt = alt;
    tableProps.cardBacking.userData.materialUrl = state.card;
    tableProps.cardBacking.userData.materialAlt = alt;
    requestMaterialTexture(state.card, 'card', 0);
    syncThumbs();
    requestDolly('card');
  } else {
    tableProps.photoGroup.visible = false;
    tableProps.cardGroup.visible = false;
    for (let i = 0; i < 2; i++) {
      tableProps.photos[i].face.userData.materialUrl = '';
      tableProps.photos[i].backing.userData.materialUrl = '';
    }
    tableProps.cardFace.userData.materialUrl = '';
    tableProps.cardBacking.userData.materialUrl = '';
    closeLightbox(false);
    syncThumbs();
    requestDolly('base');
  }
}

function setPart(partNumber) {
  const n = Number(partNumber);
  if (!Number.isFinite(n)) return;
  const clamped = Math.max(0, Math.min(4, Math.round(n)));
  const prev = state.part;
  state.part = clamped;
  if (!mounted || clamped === prev) return;
  // Return dolly on part change away from an active material part
  if ((prev === 2 && clamped !== 2 && state.images) || (prev === 3 && clamped !== 3 && state.card)) {
    requestDolly('base');
  }
}

function showImages(urls) {
  if (urls === null || urls === undefined) {
    const hadImages = Boolean(state.images);
    state.images = null;
    if (mounted && hadImages && !state.card) {
      syncTableMaterialsFromState();
    } else if (mounted && tableProps && !state.images) {
      tableProps.photoGroup.visible = false;
    }
    return;
  }
  if (Array.isArray(urls) && urls.length === 2 && typeof urls[0] === 'string' && typeof urls[1] === 'string' && urls[0] && urls[1]) {
    state.images = [urls[0], urls[1]];
    state.card = null;
    if (mounted) syncTableMaterialsFromState();
  }
}

function showCard(url) {
  if (url === null || url === undefined) {
    const hadCard = Boolean(state.card);
    state.card = null;
    if (mounted && hadCard && !state.images) {
      syncTableMaterialsFromState();
    } else if (mounted && tableProps && !state.card) {
      tableProps.cardGroup.visible = false;
    }
    return;
  }
  if (typeof url === 'string' && url.length > 0) {
    state.card = url;
    state.images = null;
    if (mounted) syncTableMaterialsFromState();
  }
}

function rebuildAvatarRole(role) {
  if (!mounted || !scene || !sceneSharedGeos || !sceneAvatarConfigs) return false;
  if (role !== 'examiner' && role !== 'partner') return false;
  const baseCfg = sceneAvatarConfigs[role];
  const oldGrp = avatarMap[role];
  if (!baseCfg || !oldGrp) return false;
  const nextSex = castState[role].sex;
  if (oldGrp.userData && oldGrp.userData.sex === nextSex) return false;

  const prevUd = oldGrp.userData || {};
  const shadows = !lastMobile;
  const builtCfg = Object.assign({}, baseCfg, { sex: nextSex });
  const newGrp = buildAvatar(builtCfg, sceneSharedGeos, shadows);
  const newUd = newGrp.userData;
  if (newUd && prevUd) {
    newUd.yaw = prevUd.yaw || 0;
    newUd.yawVel = prevUd.yawVel || 0;
    newUd.pitch = prevUd.pitch || 0;
    newUd.pitchVel = prevUd.pitchVel || 0;
    newUd.roll = prevUd.roll || 0;
    newUd.rollVel = prevUd.rollVel || 0;
    newUd.eyeYaw = prevUd.eyeYaw || 0;
    newUd.eyePitch = prevUd.eyePitch || 0;
    newUd.mouthOpen = prevUd.mouthOpen || 0;
    if (newUd.head) newUd.head.rotation.set(newUd.pitch, newUd.yaw, newUd.roll);
    if (newUd.eyes) newUd.eyes.rotation.set(newUd.eyePitch, newUd.eyeYaw, 0);
    if (newUd.mouth) {
      newUd.mouth.scale.y = MOUTH_BASE_SCALE + newUd.mouthOpen * MOUTH_SCALE_GAIN;
      newUd.mouth.position.y = newUd.mouthBaseY - newUd.mouthOpen * MOUTH_DROP_Y;
    }
  }

  scene.remove(oldGrp);
  disposeAvatar(oldGrp);
  scene.add(newGrp);

  avatarMap[role] = newGrp;
  const avIdx = avatars.indexOf(oldGrp);
  if (avIdx >= 0) avatars[avIdx] = newGrp;
  const figIdx = allFigures.indexOf(oldGrp);
  if (figIdx >= 0) allFigures[figIdx] = newGrp;
  scene.updateMatrixWorld(true);
  return true;
}

function setCast(cast) {
  if (!cast || typeof cast !== 'object') return;
  let rebuilt = false;
  ['partner', 'examiner'].forEach(role => {
    if (!(role in cast)) return;
    const entry = cast[role];
    if (typeof entry === 'string') {
      castState[role].sex = normalizeSex(entry);
    } else if (entry && typeof entry === 'object') {
      if (typeof entry.name === 'string' && entry.name.trim()) {
        castState[role].name = entry.name.trim();
      }
      castState[role].sex = normalizeSex(entry.sex);
    } else {
      castState[role].sex = 'male';
    }
    if (mounted && scene) {
      if (rebuildAvatarRole(role)) rebuilt = true;
    }
  });
  if (rebuilt && mounted && !lightboxOpen) {
    renderOnce(0);
    syncLoop();
  }
}

function setReducedMotion(bool) {
  reducedMotionOverride = Boolean(bool);
  if (mounted) {
    const activeGoal = state.images ? 'photos' : (state.card ? 'card' : 'base');
    requestDolly(activeGoal);
    syncLoop();
  }
}

function getDebugState(role) {
  if (!mounted || typeof role !== 'string') return null;
  const av = avatarMap[role];
  if (!av || !av.userData || !av.userData.head || !av.userData.mouth) return null;
  return {
    mouthOpen: Number(av.userData.mouth.scale.y),
    headYaw: Number(av.userData.head.rotation.y),
    headPitch: Number(av.userData.head.rotation.x)
  };
}

function getDebugSeats() {
  if (!mounted) return null;
  const out = {};
  ['you', 'partner', 'examiner', 'assessor'].forEach(k => {
    const obj = avatarMap[k];
    if (obj) {
      out[k] = [
        Math.round(obj.position.x * 1000) / 1000,
        Math.round(obj.position.y * 1000) / 1000,
        Math.round(obj.position.z * 1000) / 1000
      ];
    }
  });
  return out;
}

function getDebugLook() {
  return {
    yaw: Number(lookYaw),
    pitch: Number(lookPitch),
    yawMin: LOOK_YAW_MIN,
    yawMax: LOOK_YAW_MAX,
    dragging: Boolean(lookDragging),
    returning: Boolean(lookReturning)
  };
}

function getDebugCast() {
  const seen = new Set();
  ['examiner', 'partner'].forEach(role => {
    const av = avatarMap[role];
    if (av && av.userData && av.userData.sex) {
      seen.add(av.userData.sex);
    } else {
      seen.add(castState[role].sex);
    }
  });
  return {
    partner: { name: castState.partner.name, sex: castState.partner.sex },
    examiner: { name: castState.examiner.name, sex: castState.examiner.sex },
    visibleSexes: ['male', 'female'].filter(s => seen.has(s))
  };
}

function countMeshesInObject(obj) {
  if (!obj) return 0;
  let n = 0;
  obj.traverse(node => {
    if (node && node.isMesh) n++;
  });
  return n;
}

function getDebugStats() {
  if (!mounted || !renderer || !scene || !camera) return null;
  scene.updateMatrixWorld(true);
  camera.updateMatrixWorld(true);
  _projScreen.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
  _frustum.setFromProjectionMatrix(_projScreen);

  let figuresVisible = 0;
  for (let i = 0; i < allFigures.length; i++) {
    _box3.setFromObject(allFigures[i]);
    if (!_box3.isEmpty() && _frustum.intersectsBox(_box3)) {
      figuresVisible++;
    }
  }

  let medianRenderMs = 0;
  if (renderTimeCount > 0) {
    const arr = Array.from(renderTimes.subarray(0, renderTimeCount)).sort((a, b) => a - b);
    const mid = Math.floor(arr.length / 2);
    medianRenderMs = arr.length % 2 ? arr[mid] : (arr[mid - 1] + arr[mid]) * 0.5;
  }

  return {
    figuresVisible,
    drawCalls: renderer.info.render.calls,
    triangles: renderer.info.render.triangles,
    meshes: {
      total: countMeshesInObject(scene),
      examiner: countMeshesInObject(avatarMap.examiner),
      partner: countMeshesInObject(avatarMap.partner),
      assessor: countMeshesInObject(avatarMap.assessor),
      you: countMeshesInObject(avatarMap.you)
    },
    dpr: renderer.getPixelRatio(),
    shadows: Boolean(renderer.shadowMap.enabled),
    mobile: Boolean(lastMobile),
    renderSamples: renderTimeCount,
    medianRenderMs: Math.round(medianRenderMs * 1000) / 1000
  };
}

function benchRender(frames) {
  if (!mounted || !renderer || !scene || !camera || contextLost) return null;
  const n = Math.max(1, Math.min(600, Math.round(Number(frames) || 120)));
  const samples = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    updateAvatars(1 / 60, ((performance.now() - clockStart) * 0.001) + i / 60);
    updateLook(1 / 60, performance.now());
    const t0 = performance.now();
    renderer.render(scene, camera);
    samples[i] = performance.now() - t0;
  }
  const sorted = Array.from(samples).sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const medianMs = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) * 0.5;
  const p95Ms = sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))];
  return {
    frames: n,
    medianMs: Math.round(medianMs * 1000) / 1000,
    p95Ms: Math.round(p95Ms * 1000) / 1000,
    maxMs: Math.round(sorted[sorted.length - 1] * 1000) / 1000,
    dpr: renderer.getPixelRatio(),
    shadows: Boolean(renderer.shadowMap.enabled),
    mobile: Boolean(lastMobile),
    drawCalls: renderer.info.render.calls,
    triangles: renderer.info.render.triangles
  };
}

function getDebugCamera() {
  if (!mounted || !camera) return null;
  return {
    x: Math.round(camera.position.x * 10000) / 10000,
    y: Math.round(camera.position.y * 10000) / 10000,
    z: Math.round(camera.position.z * 10000) / 10000,
    tx: Math.round(camTarget.x * 10000) / 10000,
    ty: Math.round(camTarget.y * 10000) / 10000,
    tz: Math.round(camTarget.z * 10000) / 10000,
    fov: Math.round(camera.fov * 100) / 100,
    moving: Boolean(dollyPhase !== 'idle')
  };
}

function getDebugProps() {
  if (!mounted || !tableProps) return null;
  const photos = tableProps.photoGroup && tableProps.photoGroup.visible ? 2 : 0;
  const card = tableProps.cardGroup && tableProps.cardGroup.visible ? 1 : 0;
  let texturesReady = true;
  let activeBytes = 0;
  const activeUrls = [];
  if (photos === 2 && Array.isArray(state.images)) {
    activeUrls.push(state.images[0], state.images[1]);
  } else if (card === 1 && state.card) {
    activeUrls.push(state.card);
  }
  for (let i = 0; i < activeUrls.length; i++) {
    const entry = textureCache.get(activeUrls[i]);
    if (!entry || entry.status !== 'ready') {
      texturesReady = false;
    } else {
      activeBytes += entry.bytes;
    }
  }
  let totalBytes = 0;
  const textures = [];
  textureCache.forEach((entry, url) => {
    totalBytes += entry.bytes;
    textures.push({
      url: url.length > 96 ? url.slice(0, 96) : url,
      w: entry.width,
      h: entry.height,
      bytes: entry.bytes,
      status: entry.status
    });
  });
  return {
    photos,
    card,
    texturesReady,
    textureCount: textureCache.size,
    textureBytes: totalBytes,
    activeTextureBytes: activeBytes,
    liftM: Math.round(matLiftProgress * REDUCED_LIFT_M * 10000) / 10000,
    textures
  };
}

function projectObjectToViewportRect(obj) {
  if (!obj || !camera || !renderer || !renderer.domElement) return null;
  const rect = renderer.domElement.getBoundingClientRect();
  if (rect.width <= 1 || rect.height <= 1) return null;
  scene.updateMatrixWorld(true);
  camera.updateMatrixWorld(true);
  _box3.setFromObject(obj);
  if (_box3.isEmpty()) return null;
  const min = _box3.min;
  const max = _box3.max;
  let left = Infinity;
  let right = -Infinity;
  let top = Infinity;
  let bottom = -Infinity;
  for (let ix = 0; ix < 2; ix++) {
    for (let iy = 0; iy < 2; iy++) {
      for (let iz = 0; iz < 2; iz++) {
        _vProj.set(ix ? max.x : min.x, iy ? max.y : min.y, iz ? max.z : min.z).project(camera);
        const sx = rect.left + (_vProj.x * 0.5 + 0.5) * rect.width;
        const sy = rect.top + (-_vProj.y * 0.5 + 0.5) * rect.height;
        if (sx < left) left = sx;
        if (sx > right) right = sx;
        if (sy < top) top = sy;
        if (sy > bottom) bottom = sy;
      }
    }
  }
  return {
    left: Math.round(left * 10) / 10,
    top: Math.round(top * 10) / 10,
    right: Math.round(right * 10) / 10,
    bottom: Math.round(bottom * 10) / 10,
    width: Math.round((right - left) * 10) / 10,
    height: Math.round((bottom - top) * 10) / 10
  };
}

function getDebugMaterialBounds() {
  if (!mounted || !tableProps) return null;
  const photos = [];
  if (tableProps.photoGroup && tableProps.photoGroup.visible) {
    photos.push(
      projectObjectToViewportRect(tableProps.photos[0].backing),
      projectObjectToViewportRect(tableProps.photos[1].backing)
    );
  }
  const card = tableProps.cardGroup && tableProps.cardGroup.visible
    ? projectObjectToViewportRect(tableProps.cardBacking)
    : null;
  return { photos, card };
}

function getDebugLightbox() {
  return {
    open: Boolean(lightboxOpen),
    paused: !rafId
  };
}

const SPK3D = {
  supported,
  mount,
  unmount,
  isMounted,
  setActiveRole,
  setSpeaking,
  setPart,
  showImages,
  showCard,
  setCast,
  setReducedMotion,
  __debug: {
    state: getDebugState,
    seats: getDebugSeats,
    look: getDebugLook,
    cast: getDebugCast,
    stats: getDebugStats,
    bench: benchRender,
    camera: getDebugCamera,
    props: getDebugProps,
    materialBounds: getDebugMaterialBounds,
    lightbox: getDebugLightbox
  },
  version: '1'
};

if (typeof window !== 'undefined') {
  window.SPK3D = SPK3D;
  try {
    window.dispatchEvent(new CustomEvent('spk3d:ready'));
  } catch (e) {}
}
