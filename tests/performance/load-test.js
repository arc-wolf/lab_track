import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const ADMIN_IDENTITY = __ENV.ADMIN_IDENTITY || 'labadmin1';
const ADMIN_PASSWORD = __ENV.ADMIN_PASSWORD || 'LabAdmin@123';

export const options = {
  thresholds: {
    http_req_duration: ['p(95)<800'],
  },
};

export function setup() {
  const res = http.post(
    `${BASE_URL}/api/auth/token/`,
    JSON.stringify({ identity: ADMIN_IDENTITY, password: ADMIN_PASSWORD }),
    { headers: { 'Content-Type': 'application/json' } },
  );

  if (res.status !== 200) {
    throw new Error(`Failed to obtain token for load test: ${res.status} ${res.body}`);
  }
  return { token: res.json('token') };
}

export default function (data) {
  const headers = { Authorization: `Token ${data.token}` };
  const endpoints = ['overview', 'policy', 'console-map'];

  endpoints.forEach((path) => {
    const res = http.get(`${BASE_URL}/api/admin/${path}/`, { headers });
    check(res, {
      'status 200': (r) => r.status === 200,
      'rt < 800ms': (r) => r.timings.duration < 800,
    });
  });

  sleep(1);
}
