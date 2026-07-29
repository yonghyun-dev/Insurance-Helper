import { NavLink, Outlet, Route, Routes, Navigate } from 'react-router-dom';
import ShowcasePage from './pages/ShowcasePage';
import AppFlow from './pages/app/AppFlow';
import DisclaimerPage from './pages/legal/DisclaimerPage';
import PrivacyPage from './pages/legal/PrivacyPage';
import SourcesPage from './pages/legal/SourcesPage';
import AccessibilityPage from './pages/legal/AccessibilityPage';
import AdminGraphPage from './pages/admin/AdminGraphPage';
import styles from './App.module.css';

export default function App() {
  return (
    <Routes>
      <Route path="/app/*" element={<AppFlow />} />
      <Route path="/legal/disclaimer" element={<DisclaimerPage />} />
      <Route path="/legal/privacy" element={<PrivacyPage />} />
      <Route path="/legal/sources" element={<SourcesPage />} />
      <Route path="/legal/accessibility" element={<AccessibilityPage />} />
      <Route path="/admin/graph" element={<AdminGraphPage />} />
      <Route element={<ShowcaseLayout />}>
        <Route path="/showcase" element={<ShowcasePage />} />
      </Route>
      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  );
}

function ShowcaseLayout() {
  return (
    <div className={styles.shell}>
      <nav className={styles.nav}>
        <span className={styles.brand}>
          보험길잡이 <span className={styles.brandAccent}>Design System</span>
        </span>
        <div className={styles.links}>
          <NavLink
            to="/showcase"
            className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
          >
            Showcase
          </NavLink>
          <NavLink
            to="/app"
            className={({ isActive }) => (isActive ? styles.linkActive : styles.link)}
          >
            App
          </NavLink>
        </div>
      </nav>
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}
