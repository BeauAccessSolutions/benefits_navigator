"""
Template tags for displaying supportive messages to veterans.
"""

from django import template
from django.utils.safestring import mark_safe
from core.models import SupportiveMessage

register = template.Library()


# Icon mapping for display
ICON_MAP = {
    "heart": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M3.172 5.172a4 4 0 015.656 0L10 6.343l1.172-1.171a4 4 0 115.656 5.656L10 17.657l-6.828-6.829a4 4 0 010-5.656z" clip-rule="evenodd"></path></svg>""",
    "shield": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 1.944A11.954 11.954 0 012.166 5C2.056 5.649 2 6.319 2 7c0 5.225 3.34 9.67 8 11.317C14.66 16.67 18 12.225 18 7c0-.682-.057-1.35-.166-2A11.954 11.954 0 0110 1.944z" clip-rule="evenodd"></path></svg>""",
    "flag": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M3 6a3 3 0 013-3h10a1 1 0 01.8 1.6L14.25 8l2.55 3.4A1 1 0 0116 13H6a1 1 0 00-1 1v3a1 1 0 11-2 0V6z" clip-rule="evenodd"></path></svg>""",
    "star": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path></svg>""",
    "trophy": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M5 5a3 3 0 015-2.236A3 3 0 0114.83 6H16a2 2 0 110 4h-1.174a5.002 5.002 0 01-3.826 3.826V15h1a1 1 0 110 2H8a1 1 0 110-2h1v-1.174A5.002 5.002 0 015.174 10H4a2 2 0 110-4h1.17A3.001 3.001 0 015 5z" clip-rule="evenodd"></path></svg>""",
    "check": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg>""",
    "clipboard": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path d="M8 3a1 1 0 011-1h2a1 1 0 110 2H9a1 1 0 01-1-1z"></path><path d="M6 3a2 2 0 00-2 2v11a2 2 0 002 2h8a2 2 0 002-2V5a2 2 0 00-2-2 3 3 0 01-3 3H9a3 3 0 01-3-3z"></path></svg>""",
    "calendar": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z" clip-rule="evenodd"></path></svg>""",
    "clock": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clip-rule="evenodd"></path></svg>""",
    "document": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd"></path></svg>""",
    "folder": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z"></path></svg>""",
    "alert": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path></svg>""",
    "lightbulb": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1h4v1a2 2 0 11-4 0zM12 14c.015-.34.208-.646.477-.859a4 4 0 10-4.954 0c.27.213.462.519.476.859h4.002z"></path></svg>""",
    "chart": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path d="M2 11a1 1 0 011-1h2a1 1 0 011 1v5a1 1 0 01-1 1H3a1 1 0 01-1-1v-5zM8 7a1 1 0 011-1h2a1 1 0 011 1v9a1 1 0 01-1 1H9a1 1 0 01-1-1V7zM14 4a1 1 0 011-1h2a1 1 0 011 1v12a1 1 0 01-1 1h-2a1 1 0 01-1-1V4z"></path></svg>""",
    "compass": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M5.05 4.05a7 7 0 119.9 9.9L10 18.9l-4.95-4.95a7 7 0 010-9.9zM10 11a2 2 0 100-4 2 2 0 000 4z" clip-rule="evenodd"></path></svg>""",
    "medal": """<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M6 3.75A2.75 2.75 0 018.75 1h2.5A2.75 2.75 0 0114 3.75v.443c.572.055 1.14.122 1.706.2C17.053 4.582 18 5.75 18 7.07v3.469c0 1.126-.694 2.191-1.83 2.54-1.952.599-4.024.921-6.17.921s-4.219-.322-6.17-.921C2.694 12.73 2 11.665 2 10.539V7.07c0-1.321.947-2.489 2.294-2.676A41.047 41.047 0 016 4.193V3.75zm6.5 0v.325a41.622 41.622 0 00-5 0V3.75c0-.69.56-1.25 1.25-1.25h2.5c.69 0 1.25.56 1.25 1.25zM10 10a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"></path><path d="M3 15.055v-.684c.126.053.255.1.39.142 2.092.642 4.313.987 6.61.987 2.297 0 4.518-.345 6.61-.987.135-.041.264-.089.39-.142v.684c0 1.347-.985 2.53-2.363 2.686a41.454 41.454 0 01-9.274 0C3.985 17.585 3 16.402 3 15.055z"></path></svg>""",
}

# Tone to color mapping
TONE_COLORS = {
    "encouraging": "bg-blue-50 border-blue-200 text-blue-800",
    "informative": "bg-gray-50 border-gray-200 text-gray-800",
    "celebratory": "bg-green-50 border-green-200 text-green-800",
    "urgent": "bg-red-50 border-red-200 text-red-800",
    "calming": "bg-purple-50 border-purple-200 text-purple-800",
}

TONE_ICON_COLORS = {
    "encouraging": "text-blue-500",
    "informative": "text-gray-500",
    "celebratory": "text-green-500",
    "urgent": "text-red-500",
    "calming": "text-purple-500",
}


@register.simple_tag
def supportive_message(context, css_class=""):
    """
    Display a supportive message for the given context.

    Usage:
        {% load supportive_tags %}
        {% supportive_message "exam_starting" %}
        {% supportive_message "decision_denied" "mt-4" %}
    """
    message = SupportiveMessage.get_message_for_context(context)
    if not message:
        return ""

    icon_svg = ICON_MAP.get(message.icon, ICON_MAP["heart"])
    tone_class = TONE_COLORS.get(message.tone, TONE_COLORS["encouraging"])
    icon_color = TONE_ICON_COLORS.get(message.tone, "text-blue-500")

    html = f"""
    <div class="supportive-message rounded-lg border p-4 {tone_class} {css_class}">
        <div class="flex items-start gap-3">
            <div class="flex-shrink-0 {icon_color}">
                {icon_svg}
            </div>
            <p class="text-sm font-medium">{message.message}</p>
        </div>
    </div>
    """
    return mark_safe(html)


@register.inclusion_tag("core/partials/supportive_message.html", takes_context=True)
def supportive_message_card(context, message_context, extra_class=""):
    """
    Display a supportive message using a template partial.

    Usage:
        {% load supportive_tags %}
        {% supportive_message_card "exam_starting" %}
        {% supportive_message_card "decision_denied" extra_class="mt-4" %}
    """
    message = SupportiveMessage.get_message_for_context(message_context)
    return {
        "message": message,
        "icon_map": ICON_MAP,
        "tone_colors": TONE_COLORS,
        "icon_colors": TONE_ICON_COLORS,
        "extra_class": extra_class,
    }


@register.simple_tag
def get_supportive_message(context):
    """
    Get a supportive message object for use in templates.

    Usage:
        {% load supportive_tags %}
        {% get_supportive_message "exam_starting" as msg %}
        {% if msg %}
            {{ msg.message }}
        {% endif %}
    """
    return SupportiveMessage.get_message_for_context(context)
