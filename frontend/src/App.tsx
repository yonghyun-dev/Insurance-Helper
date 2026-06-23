import { NavLink, Outlet, Route, Routes, Navigate } from 'react-router-dom';
import ShowcasePage from './pages/ShowcasePage';
import AppFlow from './pages/app/AppFlow';
import styles from './App.module.css';

export default function App() {
  return (
    <Routes>
      <Route path="/app/*" element={<AppFlow />} />
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
