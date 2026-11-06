import { Navigate, Routes, Route } from 'react-router-dom'
import { Layout } from './components'
import {
  Coach,
  Games,
  GameDetail,
  Stats,
  Trends,
  Compare,
  Benchmarks,
  Players,
  PlayerDetail,
} from './pages'

function App() {
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
          <Route path="benchmarks" element={<Benchmarks />} />
        </Route>
        <Route path="players" element={<Players />} />
        <Route path="players/:playerId" element={<PlayerDetail />} />
      </Route>
    </Routes>
  )
}

export default App
