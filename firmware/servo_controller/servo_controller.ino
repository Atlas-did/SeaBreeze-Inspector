/**
 * ============================================================================
 * 海上风电运维无人机-机械臂协同系统 — 舵机控制器固件
 * ============================================================================
 * 主控: Arduino Nano (ATmega328P, CH340)
 * 舵机驱动: PCA9685 (I2C, 地址0x40)
 * 舵机: 3×SG90 (底座S1/大臂S2/小臂S3)
 * 波特率: 115200
 * 
 * 【技术选型说明】
 * 舵机控制: 选用PCA9685 I2C方案而非直接PWM，原因:
 *   1. 硬件规格已给定PCA9685驱动板，直接PWM需改硬件接线
 *   2. PCA9685是专用PWM芯片，12位精度(0.04°)，波形稳定无抖动
 *   3. 天然支持外接5V供电，与Nano电源分离，避免USB供电不足
 *   4. 仅占用A4(SDA)/A5(SCL)两根线，不占用数字引脚
 * 
 * 通信协议: 选用简单文本协议而非JSON/二进制，原因:
 *   1. 大学生团队需要串口调试时一眼看懂，Arduino IDE串口监视器直接可用
 *   2. 解析开销小，16MHz ATmega328P处理无压力
 *   3. 换行符天然作为帧边界，错误恢复简单
 * ============================================================================
 * 
 * ⚠️⚠️⚠️ 电源警告 ⚠️⚠️⚠️
 * Nano的USB接口最大输出约500mA，而3个SG90舵机同时运动时峰值电流
 * 可达750mA-1000mA，远超USB供电能力！
 * 【必须外接5V 2A独立电源给PCA9685的V+和GND供电】
 * Nano与PCA9685共地（GND相连）即可，Nano通过USB供电。
 * 不加外部电源会导致：舵机抖动、Nano反复复位、USB口保护断电。
 * ============================================================================
 * 
 * 【所需库安装】
 * 1. 打开Arduino IDE → 工具 → 管理库
 * 2. 搜索 "Adafruit PWM Servo Driver" 
 * 3. 安装 "Adafruit PCA9685 PWM Servo Driver Library" (by Adafruit)
 * 4. 会自动安装依赖 "Adafruit BusIO"
 * ============================================================================
 */

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

// =============================================================================
// 硬件引脚定义
// =============================================================================

// I2C接口（Nano硬件I2C，固定引脚不可更改）
// SDA → A4 (Arduino Nano的SDA固定接A4)
// SCL → A5 (Arduino Nano的SCL固定接A5)
// 不需要在代码中指定，Wire库自动使用这两个引脚

// PCA9685 I2C地址（默认0x40，板载A0-A5焊盘可修改地址）
#define PCA9685_ADDR 0x40

// 舵机对应的PCA9685 PWM通道号
#define CH_BASE      0   // 底座旋转舵机 (S1) → PCA9685 PWM0
#define CH_SHOULDER  1   // 大臂俯仰舵机 (S2) → PCA9685 PWM1
#define CH_ELBOW     2   // 小臂俯仰舵机 (S3) → PCA9685 PWM2

// SG90舵机的PWM脉宽范围（单位：微秒）
// SG90规格: 0°=500us, 90°=1500us, 180°=2500us
// 实际舵机有偏差，以下值需根据具体舵机微调
#define SERVO_MIN_US  500   // 0度对应的脉宽 (us)
#define SERVO_MAX_US  2500  // 180度对应的脉宽 (us)

// PCA9685 PWM频率（舵机标准50Hz，周期20ms）
#define PWM_FREQ 50

// =============================================================================
// 运动控制参数
// =============================================================================

// 平滑运动步进间隔（毫秒），每20ms移动1度
// 计算公式: 速度 = 1度 / 20ms = 50度/秒
// SG90最大速度约60度/秒，50度/秒留有裕量，避免机械冲击
#define MOVE_STEP_MS    20

// 平滑运动每步最大角度变化（度）
#define MOVE_STEP_DEG   1

// 看门狗超时时间（毫秒）
// 如果500ms内未收到新指令，自动保持当前位置（停止运动）
#define WATCHDOG_MS     500

// 上电归位角度（度）
// 90,90,90 为机械臂竖直姿态，所有关节居中
#define HOME_BASE      90
#define HOME_SHOULDER  90
#define HOME_ELBOW     90

// 串口波特率
#define BAUD_RATE 115200

// 输入缓冲区大小
#define BUFFER_SIZE 64

// =============================================================================
// 全局变量
// =============================================================================

// PCA9685驱动对象
Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(PCA9685_ADDR);

// 当前实际角度（度）
int currentAngles[3] = {HOME_BASE, HOME_SHOULDER, HOME_ELBOW};

// 目标角度（度）
int targetAngles[3] = {HOME_BASE, HOME_SHOULDER, HOME_ELBOW};

// 看门狗计时器（记录上次收到指令的时间）
unsigned long lastCommandTime = 0;

// 串口接收缓冲区
char rxBuffer[BUFFER_SIZE];
int rxIndex = 0;

// 运动是否进行中标志
bool isMoving = false;

// 上次运动步进的时间戳
unsigned long lastStepTime = 0;

// =============================================================================
// 初始化
// =============================================================================

void setup() {
  // 初始化串口通信
  Serial.begin(BAUD_RATE);
  // 等待串口就绪（ Leonardo/Micro 需要，Nano实际上不需要但保留无害）
  while (!Serial) { ; }
  
  delay(100);  // 短暂延时确保串口稳定
  
  Serial.println(F("============================================"));
  Serial.println(F("  无人机-机械臂协同系统 — 舵机控制器"));
  Serial.println(F("  版本: v1.0 | 2026"));
  Serial.println(F("============================================"));
  
  // 初始化I2C总线
  Wire.begin();
  
  // 初始化PCA9685
  pca.begin();
  // 设置PWM输出频率为50Hz（舵机标准频率）
  // 计算公式: prescale = round(25MHz / (4096 * freq)) - 1
  // 50Hz时 prescale = round(25000000 / 204800) - 1 = 121
  pca.setPWMFreq(PWM_FREQ);
  
  Serial.print(F("[INIT] PCA9685已初始化，地址0x"));
  Serial.print(PCA9685_ADDR, HEX);
  Serial.print(F("，PWM频率"));
  Serial.print(PWM_FREQ);
  Serial.println(F("Hz"));
  
  // 上电归位：所有舵机平滑移动到90度
  Serial.println(F("[INIT] 正在归位到默认姿态 (90, 90, 90)..."));
  goHome();
  
  // 初始化看门狗计时器
  lastCommandTime = millis();
  
  Serial.println(F("[INIT] 初始化完成，等待指令..."));
  Serial.println(F("提示: 发送 H 查看帮助信息"));
  Serial.println(F("============================================"));
}

// =============================================================================
// 主循环
// =============================================================================

void loop() {
  // 1. 处理串口输入
  processSerialInput();
  
  // 2. 执行平滑运动（如果目标角度与当前角度不同）
  processSmoothMotion();
  
  // 3. 看门狗检查
  checkWatchdog();
}

// =============================================================================
// 串口输入处理
// =============================================================================

void processSerialInput() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    
    // 换行符表示一条指令结束
    if (c == '\n' || c == '\r') {
      if (rxIndex > 0) {
        rxBuffer[rxIndex] = '\0';  // 字符串终止符
        parseAndExecute(rxBuffer);
        rxIndex = 0;  // 重置缓冲区索引
      }
    }
    // 普通字符，存入缓冲区（忽略回退和不可打印字符）
    else if (rxIndex < BUFFER_SIZE - 1 && c >= 32 && c <= 126) {
      rxBuffer[rxIndex++] = c;
    }
    // 缓冲区满，强制处理
    else if (rxIndex >= BUFFER_SIZE - 1) {
      rxBuffer[rxIndex] = '\0';
      parseAndExecute(rxBuffer);
      rxIndex = 0;
    }
  }
}

// =============================================================================
// 指令解析与执行
// =============================================================================

/**
 * 通信协议格式（简单文本协议）:
 * 
 * A<base>,<shoulder>,<elbow>  → 绝对角度模式，设置三个关节目标角度
 * R<base>,<shoulder>,<elbow>  → 相对增量模式，在当前角度上增减
 * H                            → 归位（Home），回到90,90,90
 * Q                            → 查询（Query），返回当前三个关节角度
 * S                            → 停止（Stop），立即停止运动
 * ?                            → 帮助信息
 * 
 * 示例:
 *   A90,45,30   → 设置目标角度为 base=90, shoulder=45, elbow=30
 *   R10,0,-5    → base增加10度, shoulder不变, elbow减少5度
 *   H           → 归位
 *   Q           → 返回 "A:90,S:45,E:30"
 */

void parseAndExecute(char* cmd) {
  // 重置看门狗（收到有效指令）
  lastCommandTime = millis();
  
  // 获取指令类型（第一个字符）
  char type = cmd[0];
  
  switch (type) {
    case 'A':  // 绝对角度模式 (Absolute)
    case 'a':
      handleAbsoluteMode(cmd + 1);
      break;
      
    case 'R':  // 相对增量模式 (Relative)
    case 'r':
      handleRelativeMode(cmd + 1);
      break;
      
    case 'H':  // 归位 (Home)
    case 'h':
      goHome();
      break;
      
    case 'Q':  // 查询 (Query)
    case 'q':
      reportAngles();
      break;
      
    case 'S':  // 停止 (Stop)
    case 's':
      emergencyStop();
      break;
      
    case '?':  // 帮助
      printHelp();
      break;
      
    default:
      Serial.print(F("[ERR] 未知指令: "));
      Serial.println(cmd);
      Serial.println(F("提示: 发送 ? 查看帮助"));
      break;
  }
}

// =============================================================================
// 绝对角度模式: A<base>,<shoulder>,<elbow>
// =============================================================================

void handleAbsoluteMode(char* params) {
  int angles[3];
  
  // 解析三个逗号分隔的整数
  if (!parseThreeInts(params, angles)) {
    Serial.println(F("[ERR] 绝对模式格式错误"));
    Serial.println(F("正确格式: A90,45,30"));
    return;
  }
  
  // 角度范围校验 (0-180度)
  for (int i = 0; i < 3; i++) {
    if (angles[i] < 0 || angles[i] > 180) {
      Serial.print(F("[ERR] 角度超出范围[0,180]: "));
      Serial.println(angles[i]);
      return;
    }
  }
  
  // 设置目标角度
  targetAngles[0] = angles[0];
  targetAngles[1] = angles[1];
  targetAngles[2] = angles[2];
  isMoving = true;
  
  Serial.print(F("[ABS] 目标角度 → Base:"));
  Serial.print(targetAngles[0]);
  Serial.print(F(" Shoulder:"));
  Serial.print(targetAngles[1]);
  Serial.print(F(" Elbow:"));
  Serial.println(targetAngles[2]);
}

// =============================================================================
// 相对增量模式: R<base_delta>,<shoulder_delta>,<elbow_delta>
// =============================================================================

void handleRelativeMode(char* params) {
  int deltas[3];
  
  if (!parseThreeInts(params, deltas)) {
    Serial.println(F("[ERR] 相对模式格式错误"));
    Serial.println(F("正确格式: R10,0,-5"));
    return;
  }
  
  // 计算目标角度 = 当前角度 + 增量
  for (int i = 0; i < 3; i++) {
    targetAngles[i] = currentAngles[i] + deltas[i];
    // 限制在0-180范围内
    targetAngles[i] = constrain(targetAngles[i], 0, 180);
  }
  isMoving = true;
  
  Serial.print(F("[REL] 增量 ("));
  Serial.print(deltas[0]);
  Serial.print(F(","));
  Serial.print(deltas[1]);
  Serial.print(F(","));
  Serial.print(deltas[2]);
  Serial.print(F(") → 目标 Base:"));
  Serial.print(targetAngles[0]);
  Serial.print(F(" Shoulder:"));
  Serial.print(targetAngles[1]);
  Serial.print(F(" Elbow:"));
  Serial.println(targetAngles[2]);
}

// =============================================================================
// 平滑运动处理
// =============================================================================

void processSmoothMotion() {
  if (!isMoving) return;
  
  unsigned long now = millis();
  
  // 每隔MOVE_STEP_MS执行一步
  if (now - lastStepTime < MOVE_STEP_MS) return;
  lastStepTime = now;
  
  bool allReached = true;
  
  for (int i = 0; i < 3; i++) {
    int diff = targetAngles[i] - currentAngles[i];
    
    if (diff == 0) continue;  // 已到位
    
    allReached = false;
    
    // 每步最多移动MOVE_STEP_DEG度
    if (abs(diff) <= MOVE_STEP_DEG) {
      currentAngles[i] = targetAngles[i];  // 最后一步直接到位
    } else {
      currentAngles[i] += (diff > 0) ? MOVE_STEP_DEG : -MOVE_STEP_DEG;
    }
    
    // 输出PWM信号
    setServoAngle(i, currentAngles[i]);
  }
  
  // 所有舵机都到达目标
  if (allReached) {
    isMoving = false;
    Serial.println(F("[OK] 运动完成"));
  }
}

// =============================================================================
// 看门狗检查
// =============================================================================

void checkWatchdog() {
  unsigned long now = millis();
  
  // 检查是否超时
  if (now - lastCommandTime > WATCHDOG_MS) {
    // 如果正在运动，则停止在当前位置
    if (isMoving) {
      isMoving = false;
      // 将目标设为当前位置（保持不动）
      targetAngles[0] = currentAngles[0];
      targetAngles[1] = currentAngles[1];
      targetAngles[2] = currentAngles[2];
      Serial.println(F("[WDOG] 看门狗触发：500ms未收到指令，保持当前位置"));
    }
  }
}

// =============================================================================
// 舵机控制底层
// =============================================================================

/**
 * 设置指定舵机的角度
 * 
 * 参数:
 *   servoIndex: 0=底座, 1=大臂, 2=小臂
 *   angle: 目标角度 (0-180度)
 * 
 * PWM脉宽计算:
 *   pulse_us = SERVO_MIN_US + angle * (SERVO_MAX_US - SERVO_MIN_US) / 180
 *   PCA9685的12位分辨率: 0-4095 对应 0-100%占空比
 *   在50Hz下: 1周期 = 20ms = 20000us
 *   ticks = pulse_us / 20000 * 4096 = pulse_us * 4096 / 20000 ≈ pulse_us / 4.88
 * 
 * Adafruit库封装了这个计算，只需调用 setPWM(channel, 0, ticks)
 */
void setServoAngle(int servoIndex, int angle) {
  // 角度限制在有效范围内
  angle = constrain(angle, 0, 180);
  
  // 将角度转换为脉宽（微秒）
  // 公式: pulse = MIN + angle * (MAX - MIN) / 180
  int pulseUs = SERVO_MIN_US + (long)angle * (SERVO_MAX_US - SERVO_MIN_US) / 180;
  
  // 获取对应通道号
  uint8_t channel;
  switch (servoIndex) {
    case 0: channel = CH_BASE; break;
    case 1: channel = CH_SHOULDER; break;
    case 2: channel = CH_ELBOW; break;
    default: return;
  }
  
  // 输出PWM（Adafruit库自动计算ticks）
  pca.writeMicroseconds(channel, pulseUs);
}

// =============================================================================
// 辅助功能
// =============================================================================

/**
 * 归位：平滑移动到默认姿态 (90, 90, 90)
 */
void goHome() {
  targetAngles[0] = HOME_BASE;
  targetAngles[1] = HOME_SHOULDER;
  targetAngles[2] = HOME_ELBOW;
  isMoving = true;
  Serial.println(F("[HOME] 正在归位到 (90, 90, 90)..."));
}

/**
 * 紧急停止：立即停止所有运动
 */
void emergencyStop() {
  isMoving = false;
  // 将目标锁定在当前位置
  targetAngles[0] = currentAngles[0];
  targetAngles[1] = currentAngles[1];
  targetAngles[2] = currentAngles[2];
  Serial.println(F("[STOP] 紧急停止，当前位置已锁定"));
}

/**
 * 上报当前三个关节的角度
 * 格式: "A:90,S:45,E:30" (Base, Shoulder, Elbow)
 */
void reportAngles() {
  Serial.print(F("A:"));
  Serial.print(currentAngles[0]);
  Serial.print(F(",S:"));
  Serial.print(currentAngles[1]);
  Serial.print(F(",E:"));
  Serial.println(currentAngles[2]);
}

/**
 * 解析三个逗号分隔的整数
 * 格式: ",10,20,30" 或 "10,20,30"
 * 成功返回true，失败返回false
 */
bool parseThreeInts(char* str, int* result) {
  // 跳过开头的逗号（如果有）
  if (str[0] == ',') str++;
  
  char* token = strtok(str, ",");
  for (int i = 0; i < 3; i++) {
    if (token == NULL) return false;
    result[i] = atoi(token);
    token = strtok(NULL, ",");
  }
  return true;
}

/**
 * 打印帮助信息
 */
void printHelp() {
  Serial.println(F(""));
  Serial.println(F("========== 指令帮助 =========="));
  Serial.println(F("A<base>,<shoulder>,<elbow>  绝对角度模式"));
  Serial.println(F("  例: A90,45,30   → 设置目标角度"));
  Serial.println(F(""));
  Serial.println(F("R<db>,<ds>,<de>             相对增量模式"));
  Serial.println(F("  例: R10,0,-5    → 在当前角度上增减"));
  Serial.println(F(""));
  Serial.println(F("H                          归位 (90,90,90)"));
  Serial.println(F("Q                          查询当前角度"));
  Serial.println(F("S                          紧急停止"));
  Serial.println(F("?                          显示本帮助"));
  Serial.println(F(""));
  Serial.println(F("角度范围: 0-180度"));
  Serial.println(F("平滑速度: 50度/秒 (每20ms移动1度)"));
  Serial.println(F("看门狗: 500ms未收到指令自动保持"));
  Serial.println(F("============================"));
}
