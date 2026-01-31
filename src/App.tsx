import { Routes, Route, useNavigate } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { ImportScreen } from "./components/import/ImportScreen";
import { TemplatesScreen } from "./components/templates/TemplatesScreen";
import { SettingsScreen } from "./components/settings/SettingsScreen";
import { AIModelScreen } from "./components/ai-model/AIModelScreen";
import { ProcessingScreen } from "./components/processing/ProcessingScreen";
import { ResultsScreen } from "./components/results/ResultsScreen";
import { HistoryScreen } from "./components/history/HistoryScreen";
import { LettersScreen } from "./components/letters/LettersScreen";
import { TeachingPointsScreen } from "./components/teaching-points/TeachingPointsScreen";
import { AuthScreen } from "./components/auth/AuthScreen";

function AuthRoute() {
  const navigate = useNavigate();
  return <AuthScreen onAuthSuccess={() => navigate("/")} />;
}

function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<ImportScreen />} />
        <Route path="/history" element={<HistoryScreen />} />
        <Route path="/letters" element={<LettersScreen />} />
        <Route path="/teaching-points" element={<TeachingPointsScreen />} />
        <Route path="/templates" element={<TemplatesScreen />} />
        <Route path="/settings" element={<SettingsScreen />} />
        <Route path="/ai-model" element={<AIModelScreen />} />
        <Route path="/processing" element={<ProcessingScreen />} />
        <Route path="/results" element={<ResultsScreen />} />
        <Route path="/auth" element={<AuthRoute />} />
      </Route>
    </Routes>
  );
}

export default App;
