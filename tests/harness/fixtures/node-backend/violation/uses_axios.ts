import axios from 'axios';

export async function fetchUser(id: string) {
  return axios.get(`/users/${id}`);
}
