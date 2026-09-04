import { createContext, useContext, useState, ReactNode } from "react";

// 支持的语言
export type Lang = "zh" | "en" | "ja" | "ko" | "fr" | "de" | "es" | "ru" | "pt" | "it" | "ar";

// 语言显示名（下拉用）
export const LANG_OPTIONS: { value: Lang; label: string }[] = [
  { value: "zh", label: "🇨🇳 中文" },
  { value: "en", label: "🇺🇸 English" },
  { value: "ja", label: "🇯🇵 日本語" },
  { value: "ko", label: "🇰🇷 한국어" },
  { value: "fr", label: "🇫🇷 Français" },
  { value: "de", label: "🇩🇪 Deutsch" },
  { value: "es", label: "🇪🇸 Español" },
  { value: "ru", label: "🇷🇺 Русский" },
  { value: "pt", label: "🇵🇹 Português" },
  { value: "it", label: "🇮🇹 Italiano" },
  { value: "ar", label: "🇸🇦 العربية" },
];

// 翻译字典：界面常用文案
const translations: Record<Lang, Record<string, string>> = {
  zh: {
    appName: "山海行", appSub: "文旅多 Agent 行程规划系统",
    login: "登录", register: "注册", username: "用户名", password: "密码",
    loginBtn: "登录", registerBtn: "注册账号", welcome: "欢迎回来",
    dashboard: "工作台", planList: "行程列表", newPlan: "新建行程", qaPlan: "问答式创建", voicePlan: "语音创建",
    reviewBoard: "审核台", memoryGraph: "记忆图谱", about: "系统说明",
    logout: "退出登录", createPlan: "立即创建行程",
    origin: "出发地", destination: "目的地", days: "天数", budget: "预算上限",
    startDate: "出发日期", endDate: "返程日期", adults: "成人", children: "儿童",
    elders: "老人", elderStatus: "老人生活状态", tags: "兴趣标签", submit: "提交给 Agent 团队",
    itinerary: "行程计划", status: "状态看板", report: "最终报告",
    editPlan: "编辑行程", save: "保存修改", price: "参考价",
    route: "出发路线", distance: "距离", duration: "时间", transport: "交通方式", driving: "驾车",
  },
  en: {
    appName: "ShanHaiXing", appSub: "Multi-Agent Travel Planning System",
    login: "Login", register: "Register", username: "Username", password: "Password",
    loginBtn: "Login", registerBtn: "Register", welcome: "Welcome back",
    dashboard: "Dashboard", planList: "Plans", newPlan: "New Plan", qaPlan: "Guided Plan", voicePlan: "Voice Plan",
    reviewBoard: "Review", memoryGraph: "Memory Graph", about: "About",
    logout: "Logout", createPlan: "Create Plan",
    origin: "Origin", destination: "Destination", days: "Days", budget: "Budget",
    startDate: "Start Date", endDate: "End Date", adults: "Adults", children: "Children",
    elders: "Elders", elderStatus: "Elder Status", tags: "Tags", submit: "Submit to Agents",
    itinerary: "Itinerary", status: "Status", report: "Report",
    editPlan: "Edit Plan", save: "Save", price: "Price",
    route: "Route", distance: "Distance", duration: "Duration", transport: "Transport", driving: "Driving",
  },
  ja: {
    appName: "山海行", appSub: "マルチエージェント旅行計画システム",
    login: "ログイン", register: "登録", username: "ユーザー名", password: "パスワード",
    loginBtn: "ログイン", registerBtn: "登録", welcome: "おかえりなさい",
    dashboard: "ダッシュボード", planList: "プラン一覧", newPlan: "新規プラン", qaPlan: "対話式作成", voicePlan: "音声作成",
    reviewBoard: "審査", memoryGraph: "記憶グラフ", about: "概要",
    logout: "ログアウト", createPlan: "プラン作成",
    origin: "出発地", destination: "目的地", days: "日数", budget: "予算",
    startDate: "出発日", endDate: "帰着日", adults: "大人", children: "子供",
    elders: "高齢者", elderStatus: "高齢者の状態", tags: "タグ", submit: "エージェントに送信",
    itinerary: "旅程", status: "ステータス", report: "レポート",
    editPlan: "プラン編集", save: "保存", price: "料金",
    route: "ルート", distance: "距離", duration: "時間", transport: "交通手段", driving: "車",
  },
  ko: {
    appName: "산해행", appSub: "멀티 에이전트 여행 계획 시스템",
    login: "로그인", register: "회원가입", username: "사용자 이름", password: "비밀번호",
    loginBtn: "로그인", registerBtn: "회원가입", welcome: "다시 오신 것을 환영합니다",
    dashboard: "대시보드", planList: "여행 목록", newPlan: "새 여행", qaPlan: "대화형 생성", voicePlan: "음성 생성",
    reviewBoard: "심사", memoryGraph: "메모리 그래프", about: "정보",
    logout: "로그아웃", createPlan: "여행 만들기",
    origin: "출발지", destination: "목적지", days: "일수", budget: "예산",
    startDate: "출발일", endDate: "귀국일", adults: "성인", children: "어린이",
    elders: "노인", elderStatus: "노인 상태", tags: "태그", submit: "에이전트에 제출",
    itinerary: "여행 일정", status: "상태", report: "보고서",
    editPlan: "여행 편집", save: "저장", price: "가격",
    route: "경로", distance: "거리", duration: "시간", transport: "교통수단", driving: "운전",
  },
  fr: {
    appName: "ShanHaiXing", appSub: "Système de planification de voyage multi-agents",
    login: "Connexion", register: "Inscription", username: "Nom d'utilisateur", password: "Mot de passe",
    loginBtn: "Connexion", registerBtn: "S'inscrire", welcome: "Bon retour",
    dashboard: "Tableau de bord", planList: "Plans", newPlan: "Nouveau plan", qaPlan: "Création guidée", voicePlan: "Création vocale",
    reviewBoard: "Révision", memoryGraph: "Graphe mémoire", about: "À propos",
    logout: "Déconnexion", createPlan: "Créer un plan",
    origin: "Départ", destination: "Destination", days: "Jours", budget: "Budget",
    startDate: "Date de départ", endDate: "Date de retour", adults: "Adultes", children: "Enfants",
    elders: "Personnes âgées", elderStatus: "État des aînés", tags: "Tags", submit: "Soumettre aux agents",
    itinerary: "Itinéraire", status: "Statut", report: "Rapport",
    editPlan: "Modifier le plan", save: "Enregistrer", price: "Prix",
    route: "Itinéraire", distance: "Distance", duration: "Durée", transport: "Transport", driving: "Voiture",
  },
  de: {
    appName: "ShanHaiXing", appSub: "Multi-Agenten-Reiseplanungssystem",
    login: "Anmelden", register: "Registrieren", username: "Benutzername", password: "Passwort",
    loginBtn: "Anmelden", registerBtn: "Registrieren", welcome: "Willkommen zurück",
    dashboard: "Dashboard", planList: "Pläne", newPlan: "Neuer Plan", qaPlan: "Geführte Erstellung", voicePlan: "Spracherstellung",
    reviewBoard: "Überprüfung", memoryGraph: "Speichergraph", about: "Über",
    logout: "Abmelden", createPlan: "Plan erstellen",
    origin: "Abfahrt", destination: "Ziel", days: "Tage", budget: "Budget",
    startDate: "Abreisedatum", endDate: "Rückreisedatum", adults: "Erwachsene", children: "Kinder",
    elders: "Ältere", elderStatus: "Status der Älteren", tags: "Tags", submit: "An Agenten senden",
    itinerary: "Reiseplan", status: "Status", report: "Bericht",
    editPlan: "Plan bearbeiten", save: "Speichern", price: "Preis",
    route: "Route", distance: "Entfernung", duration: "Dauer", transport: "Transport", driving: "Auto",
  },
  es: {
    appName: "ShanHaiXing", appSub: "Sistema de planificación de viajes multiagente",
    login: "Iniciar sesión", register: "Registrarse", username: "Usuario", password: "Contraseña",
    loginBtn: "Entrar", registerBtn: "Registrarse", welcome: "Bienvenido de nuevo",
    dashboard: "Panel", planList: "Planes", newPlan: "Nuevo plan", qaPlan: "Creación guiada", voicePlan: "Creación por voz",
    reviewBoard: "Revisión", memoryGraph: "Gráfico de memoria", about: "Acerca de",
    logout: "Salir", createPlan: "Crear plan",
    origin: "Origen", destination: "Destino", days: "Días", budget: "Presupuesto",
    startDate: "Fecha de salida", endDate: "Fecha de regreso", adults: "Adultos", children: "Niños",
    elders: "Mayores", elderStatus: "Estado de mayores", tags: "Etiquetas", submit: "Enviar a agentes",
    itinerary: "Itinerario", status: "Estado", report: "Informe",
    editPlan: "Editar plan", save: "Guardar", price: "Precio",
    route: "Ruta", distance: "Distancia", duration: "Duración", transport: "Transporte", driving: "Coche",
  },
  ru: {
    appName: "ShanHaiXing", appSub: "Мультиагентная система планирования путешествий",
    login: "Вход", register: "Регистрация", username: "Имя пользователя", password: "Пароль",
    loginBtn: "Войти", registerBtn: "Зарегистрироваться", welcome: "С возвращением",
    dashboard: "Панель", planList: "Планы", newPlan: "Новый план", qaPlan: "Пошаговое создание", voicePlan: "Голосовое создание",
    reviewBoard: "Проверка", memoryGraph: "Граф памяти", about: "О системе",
    logout: "Выйти", createPlan: "Создать план",
    origin: "Отправление", destination: "Назначение", days: "Дни", budget: "Бюджет",
    startDate: "Дата отправления", endDate: "Дата возвращения", adults: "Взрослые", children: "Дети",
    elders: "Пожилые", elderStatus: "Состояние пожилых", tags: "Теги", submit: "Отправить агентам",
    itinerary: "Маршрут", status: "Статус", report: "Отчёт",
    editPlan: "Изменить план", save: "Сохранить", price: "Цена",
    route: "Маршрут", distance: "Расстояние", duration: "Время", transport: "Транспорт", driving: "Автомобиль",
  },
  pt: {
    appName: "ShanHaiXing", appSub: "Sistema de planejamento de viagem multiagente",
    login: "Entrar", register: "Registrar", username: "Usuário", password: "Senha",
    loginBtn: "Entrar", registerBtn: "Registrar", welcome: "Bem-vindo de volta",
    dashboard: "Painel", planList: "Planos", newPlan: "Novo plano", qaPlan: "Criação guiada", voicePlan: "Criação por voz",
    reviewBoard: "Revisão", memoryGraph: "Grafo de memória", about: "Sobre",
    logout: "Sair", createPlan: "Criar plano",
    origin: "Origem", destination: "Destino", days: "Dias", budget: "Orçamento",
    startDate: "Data de partida", endDate: "Data de retorno", adults: "Adultos", children: "Crianças",
    elders: "Idosos", elderStatus: "Estado dos idosos", tags: "Tags", submit: "Enviar aos agentes",
    itinerary: "Itinerário", status: "Status", report: "Relatório",
    editPlan: "Editar plano", save: "Salvar", price: "Preço",
    route: "Rota", distance: "Distância", duration: "Duração", transport: "Transporte", driving: "Carro",
  },
  it: {
    appName: "ShanHaiXing", appSub: "Sistema di pianificazione viaggi multi-agente",
    login: "Accedi", register: "Registrati", username: "Nome utente", password: "Password",
    loginBtn: "Accedi", registerBtn: "Registrati", welcome: "Bentornato",
    dashboard: "Dashboard", planList: "Piani", newPlan: "Nuovo piano", qaPlan: "Creazione guidata", voicePlan: "Creazione vocale",
    reviewBoard: "Revisione", memoryGraph: "Grafo memoria", about: "Informazioni",
    logout: "Esci", createPlan: "Crea piano",
    origin: "Partenza", destination: "Destinazione", days: "Giorni", budget: "Budget",
    startDate: "Data di partenza", endDate: "Data di ritorno", adults: "Adulti", children: "Bambini",
    elders: "Anziani", elderStatus: "Stato anziani", tags: "Tag", submit: "Invia agli agenti",
    itinerary: "Itinerario", status: "Stato", report: "Rapporto",
    editPlan: "Modifica piano", save: "Salva", price: "Prezzo",
    route: "Percorso", distance: "Distanza", duration: "Durata", transport: "Trasporto", driving: "Auto",
  },
  ar: {
    appName: "شانهايشنغ", appSub: "نظام تخطيط السفر متعدد الوكلاء",
    login: "تسجيل الدخول", register: "تسجيل", username: "اسم المستخدم", password: "كلمة المرور",
    loginBtn: "دخول", registerBtn: "تسجيل", welcome: "مرحباً بعودتك",
    dashboard: "لوحة التحكم", planList: "الخطط", newPlan: "خطة جديدة", qaPlan: "إنشاء موجه", voicePlan: "إنشاء صوتي",
    reviewBoard: "المراجعة", memoryGraph: "رسم الذاكرة", about: "حول",
    logout: "خروج", createPlan: "إنشاء خطة",
    origin: "نقطة الانطلاق", destination: "الوجهة", days: "الأيام", budget: "الميزانية",
    startDate: "تاريخ المغادرة", endDate: "تاريخ العودة", adults: "بالغون", children: "أطفال",
    elders: "كبار السن", elderStatus: "حالة كبار السن", tags: "وسوم", submit: "إرسال إلى الوكلاء",
    itinerary: "خط سير الرحلة", status: "الحالة", report: "تقرير",
    editPlan: "تعديل الخطة", save: "حفظ", price: "السعر",
    route: "المسار", distance: "المسافة", duration: "المدة", transport: "النقل", driving: "سيارة",
  },
};

interface I18nContextType {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextType>({
  lang: "zh",
  setLang: () => {},
  t: (k) => k,
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>("zh");
  const t = (key: string) => translations[lang][key] ?? translations.zh[key] ?? key;
  return <I18nContext.Provider value={{ lang, setLang, t }}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}
