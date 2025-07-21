import { useState } from 'react';

export default function Preferences() {
  const [currency, setCurrency] = useState('USD');
  return (
    <div>
      <h1>Preferences</h1>
      <label>Default Currency
        <input value={currency} onChange={e => setCurrency(e.target.value)} />
      </label>
    </div>
  );
}
