import api from '/static/js/api.js';

export const getCurrentUser = async () => {
  try {
    const response = await api.get('/users/me');
    return response.data;
  } catch (error) {
    console.error('Get current user error:', error);
    throw error;
  }
};

export const logout = async () => {
  await api.post('/auth/logout');
  location.pathname = '/auth/login';
};
