import re
import os

file_path = r"C:\Users\Divyarajsinh\OneDrive\Documents\python\Expenzo\backend\templates\profile.html"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update Profile Card to have an ID for instant updates, and add default avatar SVG fallback if needed
# The user wants "If no avatar exists, show a default avatar." We'll just keep the lucide icon or a nice SVG.

profile_card_old = """    <div class="profile-avatar-large">
      {% if profile.avatar %}
        <img src="{{ profile.avatar }}" alt="{{ user.first_name }}" style="width: 100%; height: 100%; object-fit: cover;">
      {% else %}
        <i data-lucide="user"></i>
      {% endif %}
    </div>"""

profile_card_new = """    <div class="profile-avatar-large" id="main-avatar-display" style="position: relative; overflow: hidden; background: linear-gradient(135deg, var(--accent-primary) 0%, #4f46e5 100%);">
      {% if profile.avatar %}
        <img src="{{ profile.avatar }}" alt="{{ user.first_name }}" style="width: 100%; height: 100%; object-fit: cover;">
      {% else %}
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%">
          <path d="M 15 95 Q 15 65 50 65 Q 85 65 85 95" fill="rgba(255, 255, 255, 0.9)" />
          <rect x="42" y="45" width="16" height="15" fill="rgba(255, 255, 255, 0.85)" rx="4" />
          <circle cx="50" cy="35" r="22" fill="#ffffff" />
        </svg>
      {% endif %}
    </div>"""

content = content.replace(profile_card_old, profile_card_new)

# 2. Add Avatar File Input to the Edit Details Form
avatar_input_html = """
      <!-- Avatar Upload Section -->
      <div class="form-group" style="margin-bottom: 2rem;">
        <label class="form-label">Profile Avatar</label>
        <div style="display: flex; gap: 1rem; align-items: center; flex-wrap: wrap;">
          <input type="file" name="avatar_file" id="avatar_file" accept="image/png, image/jpeg, image/webp" class="input-control" style="flex: 1;" onchange="previewAvatar(event)">
          <input type="hidden" name="remove_avatar" id="remove_avatar" value="false">
          {% if profile.avatar %}
            <button type="button" class="btn btn-secondary" onclick="removeAvatar()" style="display: inline-flex; align-items: center; gap: 0.5rem; padding: 0.65rem 1rem; border-radius: 12px; background: rgba(244, 63, 94, 0.1); color: #f43f5e; border: 1px solid rgba(244, 63, 94, 0.2); cursor: pointer; white-space: nowrap;">
              <i data-lucide="trash-2" style="width: 16px; height: 16px;"></i> Remove Photo
            </button>
          {% endif %}
        </div>
        <small style="color: var(--text-muted); display: block; margin-top: 0.5rem;">Accepted formats: JPG, PNG, WEBP. Max size: 5MB.</small>
      </div>
"""

content = content.replace('{% csrf_token %}', '{% csrf_token %}' + avatar_input_html)

# 3. Add Change Password Section below the Edit Details Form
password_html = """
  <!-- Change Password Section -->
  <div class="glass-card" style="padding: 2rem; margin-top: 2rem;">
    <h3 style="font-size: 1.1rem; font-weight: 700; margin-bottom: 1.5rem; color: var(--text-primary);">Change Password</h3>
    <div id="password-messages" style="margin-bottom: 1rem;"></div>
    <form id="password-form" onsubmit="changePassword(event)">
      <div class="form-group">
        <label class="form-label">Current Password</label>
        <input type="password" id="current_password" class="input-control" required />
      </div>
      <div class="form-group">
        <label class="form-label">New Password</label>
        <input type="password" id="new_password" class="input-control" required minlength="8" />
      </div>
      <div class="form-group">
        <label class="form-label">Confirm New Password</label>
        <input type="password" id="confirm_password" class="input-control" required minlength="8" />
      </div>
      <button type="submit" id="btn-change-password" class="btn btn-secondary" style="width: 100%; padding: 0.75rem; border-radius: 12px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 0.5rem; margin-top: 1.5rem; background: rgba(255,255,255,0.05); color: var(--text-primary); border: 1px solid var(--border-color);">
        <i data-lucide="lock" style="width: 18px; height: 18px;"></i>
        Update Password
      </button>
    </form>
  </div>
"""

content = content.replace('</div>\n{% endblock %}', '</div>\n' + password_html + '\n</div>\n{% endblock %}')

# 4. Add JS logic for Avatar Preview, Remove, and Password Change API
js_html = """
{% block extra_js %}
<script>
  function previewAvatar(event) {
    const file = event.target.files[0];
    if (file) {
      if (file.size > 5 * 1024 * 1024) {
        alert('File is too large. Max size is 5MB.');
        event.target.value = '';
        return;
      }
      const reader = new FileReader();
      reader.onload = function(e) {
        const display = document.getElementById('main-avatar-display');
        display.innerHTML = `<img src="${e.target.result}" style="width: 100%; height: 100%; object-fit: cover;">`;
      }
      reader.readAsDataURL(file);
      document.getElementById('remove_avatar').value = "false";
    }
  }

  function removeAvatar() {
    document.getElementById('remove_avatar').value = "true";
    document.getElementById('avatar_file').value = "";
    const display = document.getElementById('main-avatar-display');
    display.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%">
          <path d="M 15 95 Q 15 65 50 65 Q 85 65 85 95" fill="rgba(255, 255, 255, 0.9)" />
          <rect x="42" y="45" width="16" height="15" fill="rgba(255, 255, 255, 0.85)" rx="4" />
          <circle cx="50" cy="35" r="22" fill="#ffffff" />
        </svg>
    `;
  }

  async function changePassword(event) {
    event.preventDefault();
    const btn = document.getElementById('btn-change-password');
    const msgBox = document.getElementById('password-messages');
    const current = document.getElementById('current_password').value;
    const newPass = document.getElementById('new_password').value;
    const confirm = document.getElementById('confirm_password').value;

    if (newPass !== confirm) {
      msgBox.innerHTML = `<div style="color: #f43f5e; font-size: 0.9rem; margin-bottom: 1rem;">New passwords do not match.</div>`;
      return;
    }

    btn.disabled = true;
    btn.innerHTML = 'Updating...';

    try {
      const response = await fetch('{% url "api_change_password" %}', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
        },
        body: JSON.stringify({
          current_password: current,
          new_password: newPass,
          confirm_password: confirm
        })
      });

      const data = await response.json();
      if (data.status === 'success') {
        msgBox.innerHTML = `<div style="color: #34d399; font-size: 0.9rem; margin-bottom: 1rem;">${data.message}</div>`;
        document.getElementById('password-form').reset();
      } else {
        msgBox.innerHTML = `<div style="color: #f43f5e; font-size: 0.9rem; margin-bottom: 1rem;">${data.message}</div>`;
      }
    } catch (err) {
      msgBox.innerHTML = `<div style="color: #f43f5e; font-size: 0.9rem; margin-bottom: 1rem;">An unexpected error occurred.</div>`;
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<i data-lucide="lock" style="width: 18px; height: 18px;"></i> Update Password`;
      lucide.createIcons();
    }
  }
</script>
{% endblock %}
"""

content = content.replace('{% endblock %}', '{% endblock %}\n' + js_html)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Profile HTML updated successfully.")
