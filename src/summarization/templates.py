"""Summary templates for structuring meeting summaries."""
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


class TemplateType(Enum):
    """Types of summary templates."""
    KEY_POINTS = "key_points"
    ACTION_ITEMS = "action_items"
    DECISIONS = "decisions"
    FULL = "full"


@dataclass
class SummaryTemplate:
    """Template for generating structured summaries.
    
    Attributes:
        template_type: Type of template
        system_prompt: System prompt for the AI model
        user_template: Template for formatting user messages
        fields: List of field names to extract
    """
    template_type: TemplateType
    system_prompt: str
    user_template: str
    fields: List[str] = field(default_factory=list)
    
    def format_user_message(self, transcript: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Format user message with transcript and context.
        
        Args:
            transcript: Raw transcript text
            context: Optional context dictionary
            
        Returns:
            Formatted user message
        """
        context_str = ""
        if context:
            context_items = [f"{k}: {v}" for k, v in context.items()]
            context_str = "\n".join(context_items)
            context_str = f"\n\nMeeting Context:\n{context_str}"
        
        return self.user_template.format(transcript=transcript, context=context_str)


class TemplateRegistry:
    """Registry of available summary templates."""
    
    # Key Points Template - extracts main topics and highlights
    KEY_POINTS = SummaryTemplate(
        template_type=TemplateType.KEY_POINTS,
        system_prompt="You are a meeting assistant that extracts key points from transcripts. "
                      "Focus on main topics, important decisions, and notable statements. "
                      "Be concise and actionable.",
        user_template="Extract the key points from this meeting transcript.\n\n"
                      "Transcript:\n{transcript}{context}\n\n"
                      "Provide 3-7 key points as a numbered list. Each point should be brief "
                      "but capture the essential information.",
        fields=["key_points"]
    )
    
    # Action Items Template - extracts tasks and follow-ups
    ACTION_ITEMS = SummaryTemplate(
        template_type=TemplateType.ACTION_ITEMS,
        system_prompt="You are a meeting assistant that identifies action items from transcripts. "
                      "Look for tasks, assignments, deadlines, and follow-up items. "
                      "Be specific about who is responsible and when tasks are due.",
        user_template="Identify all action items from this meeting transcript.\n\n"
                      "Transcript:\n{transcript}{context}\n\n"
                      "For each action item, specify:\n"
                      "- What needs to be done\n"
                      "- Who is responsible (if mentioned)\n"
                      "- Deadline (if mentioned)\n\n"
                      "Format as a numbered list. If no action items are found, state that clearly.",
        fields=["action_items", "assignees", "deadlines"]
    )
    
    # Decisions Template - extracts decisions made
    DECISIONS = SummaryTemplate(
        template_type=TemplateType.DECISIONS,
        system_prompt="You are a meeting assistant that identifies decisions made in meetings. "
                      "Look for conclusions, agreements, and formal decisions. "
                      "Be clear and specific about what was decided.",
        user_template="Identify all decisions made in this meeting transcript.\n\n"
                      "Transcript:\n{transcript}{context}\n\n"
                      "For each decision, provide:\n"
                      "- The decision made\n"
                      "- Who was involved in the decision\n"
                      "- Any relevant context\n\n"
                      "Format as a numbered list. If no explicit decisions are found, "
                      "note that only implicit conclusions were reached.",
        fields=["decisions", "stakeholders"]
    )
    
    # Full Template - comprehensive summary
    FULL = SummaryTemplate(
        template_type=TemplateType.FULL,
        system_prompt="You are a meeting assistant that creates comprehensive summaries. "
                      "Extract key points, action items, decisions, and notable moments. "
                      "Be thorough but organized. Use clear formatting.",
        user_template="Create a comprehensive summary of this meeting.\n\n"
                      "Transcript:\n{transcript}{context}\n\n"
                      "Include:\n"
                      "1. Overview (2-3 sentences)\n"
                      "2. Key Points (5-7 items)\n"
                      "3. Action Items (with assignees if mentioned)\n"
                      "4. Decisions Made\n"
                      "5. Next Steps (if any)\n\n"
                      "Be concise but capture all important information.",
        fields=["overview", "key_points", "action_items", "decisions", "next_steps"]
    )
    
    @classmethod
    def get_template(cls, template_type: TemplateType) -> SummaryTemplate:
        """Get template by type.
        
        Args:
            template_type: Type of template to retrieve
            
        Returns:
            SummaryTemplate instance
            
        Raises:
            ValueError: If template type is not recognized
        """
        templates = {
            TemplateType.KEY_POINTS: cls.KEY_POINTS,
            TemplateType.ACTION_ITEMS: cls.ACTION_ITEMS,
            TemplateType.DECISIONS: cls.DECISIONS,
            TemplateType.FULL: cls.FULL,
        }
        
        if template_type not in templates:
            raise ValueError(f"Unknown template type: {template_type}")
        
        return templates[template_type]
    
    @classmethod
    def get_all_templates(cls) -> Dict[TemplateType, SummaryTemplate]:
        """Get all available templates.
        
        Returns:
            Dictionary of all templates by type
        """
        return {
            TemplateType.KEY_POINTS: cls.KEY_POINTS,
            TemplateType.ACTION_ITEMS: cls.ACTION_ITEMS,
            TemplateType.DECISIONS: cls.DECISIONS,
            TemplateType.FULL: cls.FULL,
        }
    
    @classmethod
    def list_template_types(cls) -> List[TemplateType]:
        """List all available template types.
        
        Returns:
            List of template types
        """
        return list(TemplateType)
