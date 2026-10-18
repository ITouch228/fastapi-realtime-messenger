import api from '/static/js/core/api.js';
import { startNewChat } from '/static/js/features/chats.js';

const SEARCH_DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 2;

function createSearchResultItem(user, onSelect) {
  const item = document.createElement('div');
  item.className = 'search-result-item';

  const avatarDiv = document.createElement('div');
  avatarDiv.style.cssText =
    'width: 30px; height: 30px; border-radius: 50%; background: #ddd; display: flex; align-items: center; justify-content: center; margin-right: 10px;';
  avatarDiv.textContent = user.username[0].toUpperCase();

  const usernameSpan = document.createElement('span');
  usernameSpan.textContent = user.username;

  const wrapperDiv = document.createElement('div');
  wrapperDiv.style.display = 'flex';
  wrapperDiv.style.alignItems = 'center';
  wrapperDiv.append(avatarDiv, usernameSpan);

  item.addEventListener('click', () => {
    onSelect(user);
  });

  item.appendChild(wrapperDiv);
  return item;
}

export function initSearch({ searchInput, searchResults, userId }) {
  let searchTimeout = null;

  const renderResults = async (query) => {
    try {
      const res = await api.get('/users/search', { params: { query } });
      const users = res.data.filter((user) => user.id !== userId);

      if (users.length > 0) {
        searchResults.textContent = 'Написать пользователю:';
        users.forEach((user) => {
          searchResults.appendChild(
            createSearchResultItem(user, (selected) => {
              startNewChat(selected.id);
              searchInput.value = '';
              searchResults.style.display = 'none';
            }),
          );
        });
      } else {
        searchResults.innerHTML =
          '<div class="search-result-item">Ничего не найдено</div>';
      }
      searchResults.style.display = 'block';
    } catch (err) {
      console.error('Ошибка поиска:', err);
      searchResults.innerHTML =
        '<div class="search-result-item">Ошибка поиска</div>';
      searchResults.style.display = 'block';
    }
  };

  searchInput.addEventListener('input', function () {
    clearTimeout(searchTimeout);
    const query = this.value.trim();

    if (query.length < MIN_QUERY_LENGTH) {
      searchResults.style.display = 'none';
      return;
    }

    searchTimeout = setTimeout(() => renderResults(query), SEARCH_DEBOUNCE_MS);
  });

  // Закрытие результатов поиска при клике вне поля поиска
  document.addEventListener('click', (e) => {
    if (!searchInput.contains(e.target)) {
      searchResults.style.display = 'none';
    }
  });
}
