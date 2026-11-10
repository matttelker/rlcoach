import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components';
import { Coach } from './pages/Coach';
import { Compare } from './pages/Compare';
import { GameDetail } from './pages/GameDetail';
import { Games } from './pages/Games';
import { PlayerDetail } from './pages/PlayerDetail';
import { Players } from './pages/Players';
import { Stats } from './pages/Stats';
import { Trends } from './pages/Trends';

/** Every page inside the top bar. Stats opens on Trends, with Compare as a tab beside it. */
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Coach />} />
        <Route path="games" element={<Games />} />
        <Route path="games/:replayId" element={<GameDetail />} />
        <Route path="stats" element={<Stats />}>
          <Route index element={<Navigate to="trends" replace />} />
          <Route path="trends" element={<Trends />} />
          <Route path="compare" element={<Compare />} />
        </Route>
        <Route path="players" element={<Players />} />
        <Route path="players/:playerId" element={<PlayerDetail />} />
      </Route>
    </Routes>
  );
}
