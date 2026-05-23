"""Summary generation using OpenRouter API."""
import logging
import json
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class SummaryError(Exception):
    """Exception raised for summary generation errors."""
    pass


class ModelType(Enum):
    """Available AI models for summarization."""
    GEMINI_FLASH = "google/gemini-2.0-flash-001"
    DEEPSEEK_V3 = "deepseek/deepseek-chat"
    DEEPSEEK_Coder = "deepseek/deepseek-coder"
    
    @property
    def display_name(self) -> str:
        """Human-readable model name."""
        names = {
            ModelType.GEMINI_FLASH: "Gemini Flash 2.0",
            ModelType.DEEPSEEK_V3: "DeepSeek Chat",
            ModelType.DEEPSEEK_Coder: "DeepSeek Coder",
        }
        return names.get(self, self.value)


class SummaryGenerator:
    """Generate meeting summaries using OpenRouter API.
    
    Supports multiple template types and AI models for flexible
    summary generation from meeting transcripts.
    """
    
    DEFAULT_MODEL = ModelType.GEMINI_FLASH
    DEFAULT_MAX_TOKENS = 1024
    DEFAULT_TEMPERATURE = 0.7
    
    def __init__(self, 
                 api_key: str,
                 db=None,
                 model: ModelType = None,
                 max_tokens: int = None,
                 temperature: float = None):
        """Initialize summary generator.
        
        Args:
            api_key: OpenRouter API key
            db: Database instance for storing summaries (optional)
            model: AI model to use (defaults to Gemini Flash)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0-1.0)
        """
        self.api_key = api_key
        self.db = db
        self.model = model or self.DEFAULT_MODEL
        self.max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS
        self.temperature = temperature if temperature is not None else self.DEFAULT_TEMPERATURE
        
        # Lazy import to handle missing requests library gracefully
        self._requests = None
    
    @property
    def requests(self):
        """Lazy-load requests library."""
        if self._requests is None:
            try:
                import requests as req
                self._requests = req
            except ImportError:
                raise SummaryError(
                    "requests library required for API calls. "
                    "Install with: pip install requests"
                )
        return self._requests
    
    def _call_api(self, messages: List[Dict[str, str]]) -> str:
        """Call OpenRouter API with messages.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            
        Returns:
            API response text
            
        Raises:
            SummaryError: If API call fails
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/chronicle",
            "X-Title": "Chronicle Meeting Summarizer"
        }
        
        payload = {
            "model": self.model.value,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        try:
            response = self.requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            
            data = response.json()
            
            if "choices" not in data or not data["choices"]:
                raise SummaryError("Invalid API response: no choices returned")
            
            return data["choices"][0]["message"]["content"]
            
        except self.requests.exceptions.Timeout:
            raise SummaryError("API request timed out")
        except self.requests.exceptions.HTTPError as e:
            error_msg = f"API HTTP error: {e.response.status_code}"
            try:
                error_data = e.response.json()
                error_msg += f" - {error_data.get('error', {}).get('message', '')}"
            except Exception:
                pass
            raise SummaryError(error_msg)
        except self.requests.exceptions.RequestException as e:
            raise SummaryError(f"API request failed: {str(e)}")
        except json.JSONDecodeError:
            raise SummaryError("Invalid JSON response from API")
    
    def generate(self, 
                 transcript: str,
                 template,
                 context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate summary from transcript using specified template.
        
        Args:
            transcript: Raw transcript text
            template: SummaryTemplate to use
            context: Optional context (session name, participants, etc.)
            
        Returns:
            Dictionary with summary results
            
        Raises:
            SummaryError: If generation fails
        """
        if not transcript or not transcript.strip():
            raise SummaryError("Transcript cannot be empty")
        
        if not self.api_key:
            raise SummaryError("API key required for summary generation")
        
        # Format messages
        messages = [
            {"role": "system", "content": template.system_prompt},
            {"role": "user", "content": template.format_user_message(transcript, context)}
        ]
        
        try:
            result = self._call_api(messages)
            
            summary = {
                "content": result,
                "template_type": template.template_type.value,
                "model_used": self.model.value,
                "fields": template.fields
            }
            
            logger.info(f"Generated {template.template_type.value} summary using {self.model.display_name}")
            return summary
            
        except SummaryError:
            raise
        except Exception as e:
            raise SummaryError(f"Summary generation failed: {str(e)}")
    
    def generate_key_points(self, 
                            transcript: str,
                            context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate key points summary.
        
        Args:
            transcript: Raw transcript text
            context: Optional context
            
        Returns:
            Summary dictionary
        """
        from .templates import TemplateRegistry, TemplateType
        template = TemplateRegistry.get_template(TemplateType.KEY_POINTS)
        return self.generate(transcript, template, context)
    
    def generate_action_items(self, 
                               transcript: str,
                               context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate action items summary.
        
        Args:
            transcript: Raw transcript text
            context: Optional context
            
        Returns:
            Summary dictionary
        """
        from .templates import TemplateRegistry, TemplateType
        template = TemplateRegistry.get_template(TemplateType.ACTION_ITEMS)
        return self.generate(transcript, template, context)
    
    def generate_decisions(self, 
                          transcript: str,
                          context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate decisions summary.
        
        Args:
            transcript: Raw transcript text
            context: Optional context
            
        Returns:
            Summary dictionary
        """
        from .templates import TemplateRegistry, TemplateType
        template = TemplateRegistry.get_template(TemplateType.DECISIONS)
        return self.generate(transcript, template, context)
    
    def generate_full_summary(self, 
                              transcript: str,
                              context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate comprehensive full summary.
        
        Args:
            transcript: Raw transcript text
            context: Optional context
            
        Returns:
            Summary dictionary
        """
        from .templates import TemplateRegistry, TemplateType
        template = TemplateRegistry.get_template(TemplateType.FULL)
        return self.generate(transcript, template, context)
    
    def generate_all(self, 
                     transcript: str,
                     context: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
        """Generate all types of summaries.
        
        Args:
            transcript: Raw transcript text
            context: Optional context
            
        Returns:
            Dictionary with all summary types
        """
        results = {}
        
        try:
            results['key_points'] = self.generate_key_points(transcript, context)
        except SummaryError as e:
            logger.error(f"Key points generation failed: {e}")
            results['key_points'] = {"error": str(e)}
        
        try:
            results['action_items'] = self.generate_action_items(transcript, context)
        except SummaryError as e:
            logger.error(f"Action items generation failed: {e}")
            results['action_items'] = {"error": str(e)}
        
        try:
            results['decisions'] = self.generate_decisions(transcript, context)
        except SummaryError as e:
            logger.error(f"Decisions generation failed: {e}")
            results['decisions'] = {"error": str(e)}
        
        try:
            results['full'] = self.generate_full_summary(transcript, context)
        except SummaryError as e:
            logger.error(f"Full summary generation failed: {e}")
            results['full'] = {"error": str(e)}
        
        return results
    
    def store_summary(self, 
                      session_id: int, 
                      summary_type: str, 
                      content: str,
                      model_used: str) -> Optional[int]:
        """Store summary in database.
        
        Args:
            session_id: Session ID
            summary_type: Type of summary (key_points, action_items, etc.)
            content: Summary content
            model_used: AI model used
            
        Returns:
            Summary ID if stored, None if no database
        """
        if not self.db:
            logger.warning("No database configured, summary not stored")
            return None
        
        try:
            summary_id = self.db.add_summary(
                session_id=session_id,
                summary_type=summary_type,
                content=content,
                model_used=model_used
            )
            logger.info(f"Stored {summary_type} summary for session {session_id}")
            return summary_id
        except Exception as e:
            logger.error(f"Failed to store summary: {e}")
            return None
    
    def generate_and_store(self, 
                          transcript: str,
                          session_id: int,
                          summary_type: str = "full",
                          context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate summary and store in database.
        
        Args:
            transcript: Raw transcript text
            session_id: Session ID for storage
            summary_type: Type of summary to generate
            context: Optional context
            
        Returns:
            Summary dictionary including stored ID
        """
        from .templates import TemplateRegistry, TemplateType
        
        type_map = {
            "key_points": TemplateType.KEY_POINTS,
            "action_items": TemplateType.ACTION_ITEMS,
            "decisions": TemplateType.DECISIONS,
            "full": TemplateType.FULL,
        }
        
        template_type = type_map.get(summary_type, TemplateType.FULL)
        template = TemplateRegistry.get_template(template_type)
        
        result = self.generate(transcript, template, context)
        
        # Store in database
        summary_id = self.store_summary(
            session_id=session_id,
            summary_type=summary_type,
            content=result["content"],
            model_used=result["model_used"]
        )
        
        result["session_id"] = session_id
        if summary_id:
            result["summary_id"] = summary_id
        
        return result
