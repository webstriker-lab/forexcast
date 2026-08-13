import { BrowserRouter, Routes, Route } from 'react-router-dom'

function Home() {
  return <div>ForexCast</div>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
      </Routes>
    </BrowserRouter>
  )
}
