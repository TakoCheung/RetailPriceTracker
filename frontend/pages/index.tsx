import { useEffect, useState } from 'react';

export default function Home() {
  const [data, setData] = useState<string>('');
  useEffect(() => {
    fetch('/api/hello').then(res => res.text()).then(setData);
  }, []);
  return (<div>
    <h1>Retail Price Tracker</h1>
    <p>{data}</p>
  </div>);
}
